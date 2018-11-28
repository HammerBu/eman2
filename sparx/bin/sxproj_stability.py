#!/usr/bin/env python
from __future__ import print_function
#
# Author: 
# Copyright (c) 2012 The University of Texas - Houston Medical School
#
# This software is issued under a joint BSD/GNU license. You may use the
# source code in this file under either license. However, note that the
# complete EMAN2 and SPARX software packages have some GPL dependencies,
# so you are responsible for compliance with the licenses of these packages
# if you opt to use BSD licensing. The warranty disclaimer below holds
# in either instance.
#
# This complete copyright notice must be included in any revised version of the
# source code. Additional authorship citations may be added, but existing
# author citations must be preserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307 USA
#
#

import EMAN2
import EMAN2_cppwrap
import applications
import filter
import fundamentals
import global_def
import math
import mpi
import numpy
import optparse
import os
import pixel_error
import sparx_applications
import sparx_filter
import sparx_fundamentals
import sparx_global_def
import sparx_pixel_error
import sparx_utilities
import sys
import time
import utilities

from builtins import range
'''
In this program, there are two ways of testing the stability of the projection.

The first one is to use the idea of moving average, which is by default. In this idea, for
each projection, we select N-1 closet projections and test the 2D alignment stability of
these N projections. Obviously, the computational and the storage burden of this solution
is huge when the number of particles are of 10^5 scale.

The second idea is to group all projections into a certain of number of groups such that 
each group has roughly N projections. We perform the 2D alignment stability test for 
each group. Compared to the first solution, this solution is N times faster and the 
storage is also N times less.

The output of the program, in both cases, is a stack of averages. In the header of the
average, the attribute "members" record the particle number that belongs to this group.
the attribute "pix_err" record the pixel error of each particle. If it is mirror unstable,
the pixel error would be 99999.99. For the simplicity of the program, there are actually
(number of processors used) stacks of averages, since each processor will write its own
stack. If indeed only one stack is desired, one could use sxcpy.py to concatenate all 
stacks into one stack.
'''

def main():

	progname = os.path.basename(sys.argv[0])
	usage = progname + " proj_stack output_averages --MPI"
	parser = optparse.OptionParser(usage, version=sparx_global_def.SPARXVERSION)

	parser.add_option("--img_per_group",type="int"         ,	default=100  ,				help="number of images per group" )
	parser.add_option("--radius", 		type="int"         ,	default=-1   ,				help="radius for alignment" )
	parser.add_option("--xr",           type="string"      ,    default="2 1",              help="range for translation search in x direction, search is +/xr")
	parser.add_option("--yr",           type="string"      ,    default="-1",               help="range for translation search in y direction, search is +/yr (default = same as xr)")
	parser.add_option("--ts",           type="string"      ,    default="1 0.5",            help="step size of the translation search in both directions, search is -xr, -xr+ts, 0, xr-ts, xr, can be fractional")
	parser.add_option("--iter", 		type="int"         ,	default=30,                 help="number of iterations within alignment (default = 30)" )
	parser.add_option("--num_ali",      type="int"     	   ,    default=5,         			help="number of alignments performed for stability (default = 5)" )
	parser.add_option("--thld_err",     type="float"       ,    default=1.0,         		help="threshold of pixel error (default = 1.732)" )
	parser.add_option("--grouping" , 	type="string"      ,	default="GRP",				help="do grouping of projections: PPR - per projection, GRP - different size groups, exclusive (default), GEV - grouping equal size")
	parser.add_option("--delta",        type="float"       ,    default=-1.0,         		help="angular step for reference projections (required for GEV method)")
	parser.add_option("--fl",           type="float"       ,    default=0.3,                help="cut-off frequency of hyperbolic tangent low-pass Fourier filter")
	parser.add_option("--aa",           type="float"       ,    default=0.2,                help="fall-off of hyperbolic tangent low-pass Fourier filter")
	parser.add_option("--CTF",          action="store_true",    default=False,              help="Consider CTF correction during the alignment ")
	parser.add_option("--MPI" , 		action="store_true",	default=False,				help="use MPI version")

	(options,args) = parser.parse_args()
	

	sys.argv = mpi.mpi_init(len(sys.argv), sys.argv)
	myid = mpi.mpi_comm_rank(mpi.MPI_COMM_WORLD)
	number_of_proc = mpi.mpi_comm_size(mpi.MPI_COMM_WORLD)
	main_node = 0

	if len(args) == 2:
		stack  = args[0]
		outdir = args[1]
	else:
		sparx_global_def.ERROR("incomplete list of arguments", "sxproj_stability", 1, myid=myid)
		exit()
	if not options.MPI:
		sparx_global_def.ERROR("Non-MPI not supported!", "sxproj_stability", myid=myid)
		exit()		 

	if global_def.CACHE_DISABLE:
		sparx_utilities.disable_bdb_cache()
	global_def.BATCH = True

	#if os.path.exists(outdir):  ERROR('Output directory exists, please change the name and restart the program', "sxproj_stability", 1, myid)
	#mpi_barrier(MPI_COMM_WORLD)

	
	img_per_grp = options.img_per_group
	radius = options.radius
	ite = options.iter
	num_ali = options.num_ali
	thld_err = options.thld_err

	xrng        = sparx_utilities.get_input_from_string(options.xr)
	if  options.yr == "-1":  yrng = xrng
	else          :  yrng = sparx_utilities.get_input_from_string(options.yr)
	step        = sparx_utilities.get_input_from_string(options.ts)


	if myid == main_node:
		nima = EMAN2_cppwrap.EMUtil.get_image_count(stack)
		img  = sparx_utilities.get_image(stack)
		nx   = img.get_xsize()
		ny   = img.get_ysize()
	else:
		nima = 0
		nx = 0
		ny = 0
	nima = sparx_utilities.bcast_number_to_all(nima)
	nx   = sparx_utilities.bcast_number_to_all(nx)
	ny   = sparx_utilities.bcast_number_to_all(ny)
	if radius == -1: radius = nx/2-2
	mask = sparx_utilities.model_circle(radius, nx, nx)

	st = time.time()
	if options.grouping == "GRP":
		if myid == main_node:
			print("  A  ",myid,"  ",time.time()-st)
			proj_attr = EMAN2_cppwrap.EMUtil.get_all_attributes(stack, "xform.projection")
			proj_params = []
			for i in range(nima):
				dp = proj_attr[i].get_params("spider")
				phi, theta, psi, s2x, s2y = dp["phi"], dp["theta"], dp["psi"], -dp["tx"], -dp["ty"]
				proj_params.append([phi, theta, psi, s2x, s2y])

			# Here is where the grouping is done, I didn't put enough annotation in the group_proj_by_phitheta,
			# So I will briefly explain it here
			# proj_list  : Returns a list of list of particle numbers, each list contains img_per_grp particle numbers
			#              except for the last one. Depending on the number of particles left, they will either form a
			#              group or append themselves to the last group
			# angle_list : Also returns a list of list, each list contains three numbers (phi, theta, delta), (phi, 
			#              theta) is the projection angle of the center of the group, delta is the range of this group
			# mirror_list: Also returns a list of list, each list contains img_per_grp True or False, which indicates
			#              whether it should take mirror position.
			# In this program angle_list and mirror list are not of interest.

			proj_list_all, angle_list, mirror_list = sparx_utilities.group_proj_by_phitheta(proj_params, img_per_grp=img_per_grp)
			del proj_params
			print("  B  number of groups  ",myid,"  ",len(proj_list_all),time.time()-st)
		mpi.mpi_barrier(mpi.MPI_COMM_WORLD)

		# Number of groups, actually there could be one or two more groups, since the size of the remaining group varies
		# we will simply assign them to main node.
		n_grp = nima/img_per_grp-1

		# Divide proj_list_all equally to all nodes, and becomes proj_list
		proj_list = []
		for i in range(n_grp):
			proc_to_stay = i%number_of_proc
			if proc_to_stay == main_node:
				if myid == main_node: 	proj_list.append(proj_list_all[i])
			elif myid == main_node:
				mpi.mpi_send(len(proj_list_all[i]), 1, mpi.MPI_INT, proc_to_stay, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)
				mpi.mpi_send(proj_list_all[i], len(proj_list_all[i]), mpi.MPI_INT, proc_to_stay, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)
			elif myid == proc_to_stay:
				img_per_grp = mpi.mpi_recv(1, mpi.MPI_INT, main_node, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)
				img_per_grp = int(img_per_grp[0])
				temp = mpi.mpi_recv(img_per_grp, mpi.MPI_INT, main_node, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)
				proj_list.append(list(map(int, temp)))
				del temp
			mpi.mpi_barrier(mpi.MPI_COMM_WORLD)
		print("  C  ",myid,"  ",time.time()-st)
		if myid == main_node:
			# Assign the remaining groups to main_node
			for i in range(n_grp, len(proj_list_all)):
				proj_list.append(proj_list_all[i])
			del proj_list_all, angle_list, mirror_list


	#   Compute stability per projection projection direction, equal number assigned, thus overlaps
	elif options.grouping == "GEV":
		if options.delta == -1.0: sparx_global_def.ERROR("Angular step for reference projections is required for GEV method","sxproj_stability",1)
		refproj = sparx_utilities.even_angles(options.delta)
		img_begin, img_end = sparx_applications.MPI_start_end(len(refproj), number_of_proc, myid)
		# Now each processor keeps its own share of reference projections
		refprojdir = refproj[img_begin: img_end]
		del refproj

		ref_ang = [0.0]*(len(refprojdir)*2)
		for i in range(len(refprojdir)):
			ref_ang[i*2]   = refprojdir[0][0]
			ref_ang[i*2+1] = refprojdir[0][1]+i*0.1

		print("  A  ",myid,"  ",time.time()-st)
		proj_attr = EMAN2_cppwrap.EMUtil.get_all_attributes(stack, "xform.projection")
		#  the solution below is very slow, do not use it unless there is a problem with the i/O
		"""
		for i in xrange(number_of_proc):
			if myid == i:
				proj_attr = EMUtil.get_all_attributes(stack, "xform.projection")
			mpi_barrier(MPI_COMM_WORLD)
		"""
		print("  B  ",myid,"  ",time.time()-st)

		proj_ang = [0.0]*(nima*2)
		for i in range(nima):
			dp = proj_attr[i].get_params("spider")
			proj_ang[i*2]   = dp["phi"]
			proj_ang[i*2+1] = dp["theta"]
		print("  C  ",myid,"  ",time.time()-st)
		asi = EMAN2_cppwrap.Util.nearestk_to_refdir(proj_ang, ref_ang, img_per_grp)
		del proj_ang, ref_ang
		proj_list = []
		for i in range(len(refprojdir)):
			proj_list.append(asi[i*img_per_grp:(i+1)*img_per_grp])
		del asi
		print("  D  ",myid,"  ",time.time()-st)
		#from sys import exit
		#exit()


	#   Compute stability per projection
	elif options.grouping == "PPR":
		print("  A  ",myid,"  ",time.time()-st)
		proj_attr = EMAN2_cppwrap.EMUtil.get_all_attributes(stack, "xform.projection")
		print("  B  ",myid,"  ",time.time()-st)
		proj_params = []
		for i in range(nima):
			dp = proj_attr[i].get_params("spider")
			phi, theta, psi, s2x, s2y = dp["phi"], dp["theta"], dp["psi"], -dp["tx"], -dp["ty"]
			proj_params.append([phi, theta, psi, s2x, s2y])
		img_begin, img_end = sparx_applications.MPI_start_end(nima, number_of_proc, myid)
		print("  C  ",myid,"  ",time.time()-st)
		proj_list, mirror_list = sparx_utilities.nearest_proj(proj_params, img_per_grp, list(range(img_begin, img_begin+1)))#range(img_begin, img_end))
		refprojdir = proj_params[img_begin: img_end]
		del proj_params, mirror_list
		print("  D  ",myid,"  ",time.time()-st)
	else:  sparx_global_def.ERROR("Incorrect projection grouping option","sxproj_stability",1)
	"""
	for i in xrange(len(proj_list)):
		write_text_file(proj_list[i],"projlist%06d_%04d"%(i,myid))
	"""

	###########################################################################################################
	# Begin stability test
	#if myid == 0:
	#	from utilities import read_text_file
	#	proj_list[0] = map(int, read_text_file("lggrpp0.txt"))


	aveList = [sparx_utilities.model_blank(nx,ny)]*len(proj_list)
	if options.grouping == "GRP":  refprojdir = [[0.0,0.0,-1.0]]*len(proj_list)
	for i in range(len(proj_list)):
		print("  E  ",myid,"  ",time.time()-st)
		class_data = EMAN2_cppwrap.EMData.read_images(stack, proj_list[i])
		#print "  R  ",myid,"  ",time()-st
		if options.CTF :
			for im in range(len(class_data)):  #  MEM LEAK!!
				atemp = class_data[im].copy()
				btemp = sparx_filter.filt_ctf(atemp, atemp.get_attr("ctf"), binary=1)
				class_data[im] = btemp
				#class_data[im] = filt_ctf(class_data[im], class_data[im].get_attr("ctf"), binary=1)
		for im in class_data:
			try:
				t = im.get_attr("xform.align2d") # if they are there, no need to set them!
			except:
				try:
					t = im.get_attr("xform.projection")
					d = t.get_params("spider")
					sparx_utilities.set_params2D(im, [0.0,-d["tx"],-d["ty"],0,1.0])
				except:
					sparx_utilities.set_params2D(im, [0.0, 0.0, 0.0, 0, 1.0])
		#print "  F  ",myid,"  ",time()-st
		# Here, we perform realignment num_ali times
		all_ali_params = []
		for j in range(num_ali):
			if( xrng[0] == 0.0 and yrng[0] == 0.0 ):
				avet = sparx_applications.ali2d_ras(class_data, randomize = True, ir = 1, ou = radius, rs = 1, step = 1.0, dst = 90.0, maxit = ite, check_mirror = True, FH=options.fl, FF=options.aa)
			else:
				avet = sparx_applications.within_group_refinement(class_data, mask, True, 1, radius, 1, xrng, yrng, step, 90.0, ite, options.fl, options.aa)
			ali_params = []
			for im in range(len(class_data)):
				alpha, sx, sy, mirror, scale = sparx_utilities.get_params2D(class_data[im])
				ali_params.extend( [alpha, sx, sy, mirror] )
			all_ali_params.append(ali_params)
		#aveList[i] = avet
		#print "  G  ",myid,"  ",time()-st
		del ali_params
		# We determine the stability of this group here.
		# stable_set contains all particles deemed stable, it is a list of list
		# each list has two elements, the first is the pixel error, the second is the image number
		# stable_set is sorted based on pixel error
		#from utilities import write_text_file
		#write_text_file(all_ali_params, "all_ali_params%03d.txt"%myid)
		stable_set, mir_stab_rate, average_pix_err = sparx_pixel_error.multi_align_stability(all_ali_params, 0.0, 10000.0, thld_err, False, 2*radius+1)
		#print "  H  ",myid,"  ",time()-st
		if(len(stable_set) > 5):
			stable_set_id = []
			members = []
			pix_err = []
			# First put the stable members into attr 'members' and 'pix_err'
			for s in stable_set:
				# s[1] - number in this subset
				stable_set_id.append(s[1])
				# the original image number
				members.append(proj_list[i][s[1]])
				pix_err.append(s[0])
			# Then put the unstable members into attr 'members' and 'pix_err'
			avet.to_zero()
			if options.grouping == "GRP":
				aphi = 0.0
				atht = 0.0
				vphi = 0.0
				vtht = 0.0
			l = -1
			for j in range(len(proj_list[i])):
				#  Here it will only work if stable_set_id is sorted in the increasing number, see how l progresses
				if j in stable_set_id:
					l += 1
					avet += sparx_fundamentals.rot_shift2D(class_data[j], stable_set[l][2][0], stable_set[l][2][1], stable_set[l][2][2], stable_set[l][2][3] )
					if options.grouping == "GRP":
						phi, theta, psi, sxs, sys = sparx_utilities.get_params_proj(class_data[j])
						if( theta > 90.0):
							phi = (phi+540.0)%360.0
							theta = 180.0 - theta
						aphi += phi
						atht += theta
						vphi += phi*phi
						vtht += theta*theta
				else:
					members.append(proj_list[i][j])
					pix_err.append(99999.99)
			aveList[i] = avet.copy()
			if l>1 :
				l += 1
				aveList[i] /= l
				if options.grouping == "GRP":
					aphi /= l
					atht /= l
					vphi = (vphi - l*aphi*aphi)/l
					vtht = (vtht - l*atht*atht)/l
					refprojdir[i] = [aphi, atht, (numpy.sqrt(max(vphi,0.0))+numpy.sqrt(max(vtht,0.0)))/2.0]

			# Here more information has to be stored, PARTICULARLY WHAT IS THE REFERENCE DIRECTION
			aveList[i].set_attr('members', members)
			aveList[i].set_attr('refprojdir',refprojdir[i])
			aveList[i].set_attr('pixerr', pix_err)
		else:
			print(" empty group ",i, refprojdir[i])
			aveList[i].set_attr('members',[-1])
			aveList[i].set_attr('refprojdir',refprojdir[i])
			aveList[i].set_attr('pixerr', [99999.])

	del class_data

	if myid == main_node:
		km = 0
		for i in range(number_of_proc):
			if i == main_node :
				for im in range(len(aveList)):
					aveList[im].write_image(args[1], km)
					km += 1
			else:
				nl = mpi.mpi_recv(1, mpi.MPI_INT, i, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)
				nl = int(nl[0])
				for im in range(nl):
					ave = sparx_utilities.recv_EMData(i, im+i+70000)
					nm = mpi.mpi_recv(1, mpi.MPI_INT, i, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)
					nm = int(nm[0])
					members = mpi.mpi_recv(nm, mpi.MPI_INT, i, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)
					ave.set_attr('members', list(map(int, members)))
					members = mpi.mpi_recv(nm, mpi.MPI_FLOAT, i, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)
					ave.set_attr('pixerr', list(map(float, members)))
					members = mpi.mpi_recv(3, mpi.MPI_FLOAT, i, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)
					ave.set_attr('refprojdir', list(map(float, members)))
					ave.write_image(args[1], km)
					km += 1
	else:
		mpi.mpi_send(len(aveList), 1, mpi.MPI_INT, main_node, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)
		for im in range(len(aveList)):
			sparx_utilities.send_EMData(aveList[im], main_node,im+myid+70000)
			members = aveList[im].get_attr('members')
			mpi.mpi_send(len(members), 1, mpi.MPI_INT, main_node, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)
			mpi.mpi_send(members, len(members), mpi.MPI_INT, main_node, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)
			members = aveList[im].get_attr('pixerr')
			mpi.mpi_send(members, len(members), mpi.MPI_FLOAT, main_node, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)
			try:
				members = aveList[im].get_attr('refprojdir')
				mpi.mpi_send(members, 3, mpi.MPI_FLOAT, main_node, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)
			except:
				mpi.mpi_send([-999.0,-999.0,-999.0], 3, mpi.MPI_FLOAT, main_node, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)

	global_def.BATCH = False
	mpi.mpi_barrier(mpi.MPI_COMM_WORLD)
	mpi.mpi_finalize()

if __name__=="__main__":
	main()
