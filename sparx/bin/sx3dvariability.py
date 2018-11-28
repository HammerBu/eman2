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
from builtins import range
import EMAN2
import EMAN2_cppwrap
import EMAN2db
import applications
import filter
import fundamentals
import global_def
import logger
import math
import morphology
import mpi
import numpy
import numpy as np
import optparse
import os
import projection
import reconstruction
import sets
import sparx
import sparx_applications
import sparx_filter
import sparx_fundamentals
import sparx_global_def
import sparx_logger
import sparx_morphology
import sparx_projection
import sparx_reconstruction
import sparx_statistics
import sparx_utilities
import statistics
import string
import sys
import time
import utilities

"""
Instruction:
nohup mpirun -np  64   --hostfile ./node4567.txt  sx3dvariability.py bdb:data/data \
  --output_dir=var3d  --window=300 --var3D=var.hdf --img_per_grp=100 \
      --CTF>var3d/printout &
 1. Always use small decimation rate in the first run if one has no clue about the 3D \
   variability of the data. In addition, one can skip low pass filteration when decimation \
   rate is small and this can significantly speed up computation.
 2. Check the decimated image size. It is better that the targeted decimation image size
    consists of smallprimes, 2, 3, 5...
 3. The program estimates the possible largest decimation rate.
"""
def main():

	def params_3D_2D_NEW(phi, theta, psi, s2x, s2y, mirror):
		# the final ali2d parameters already combine shifts operation first and rotation operation second for parameters converted from 3D
		if mirror:
			m = 1
			alpha, sx, sy, scalen = sparx_utilities.compose_transform2(0, s2x, s2y, 1.0, 540.0-psi, 0, 0, 1.0)
		else:
			m = 0
			alpha, sx, sy, scalen = sparx_utilities.compose_transform2(0, s2x, s2y, 1.0, 360.0-psi, 0, 0, 1.0)
		return  alpha, sx, sy, m
	
	progname = os.path.basename(sys.argv[0])
	usage = progname + " prj_stack  --ave2D= --var2D=  --ave3D= --var3D= --img_per_grp= --fl=  --aa=   --sym=symmetry --CTF"
	parser = optparse.OptionParser(usage, version=sparx_global_def.SPARXVERSION)
	
	parser.add_option("--output_dir",   type="string"	   ,	default="./",				help="Output directory")
	parser.add_option("--ave2D",		type="string"	   ,	default=False,				help="Write to the disk a stack of 2D averages")
	parser.add_option("--var2D",		type="string"	   ,	default=False,				help="Write to the disk a stack of 2D variances")
	parser.add_option("--ave3D",		type="string"	   ,	default=False,				help="Write to the disk reconstructed 3D average")
	parser.add_option("--var3D",		type="string"	   ,	default=False,				help="Compute 3D variability (time consuming!)")
	parser.add_option("--img_per_grp",	type="int"         ,	default=100,	     	    help="Number of neighbouring projections.(Default is 100)")
	parser.add_option("--no_norm",		action="store_true",	default=False,				help="Do not use normalization.(Default is to apply normalization)")
	#parser.add_option("--radius", 	    type="int"         ,	default=-1   ,				help="radius for 3D variability" )
	parser.add_option("--npad",			type="int"         ,	default=2    ,				help="Number of time to pad the original images.(Default is 2 times padding)")
	parser.add_option("--sym" , 		type="string"      ,	default="c1",				help="Symmetry. (Default is no symmetry)")
	parser.add_option("--fl",			type="float"       ,	default=0.0,				help="Low pass filter cutoff in absolute frequency (0.0 - 0.5) and is applied to decimated image. (Default - no filtration)")
	parser.add_option("--aa",			type="float"       ,	default=0.02 ,				help="Fall off of the filter. Use default value if user has no clue about falloff (Default value is 0.02)")
	parser.add_option("--CTF",			action="store_true",	default=False,				help="Use CFT correction.(Default is no CTF correction)")
	#parser.add_option("--MPI" , 		action="store_true",	default=False,				help="use MPI version")
	#parser.add_option("--radiuspca", 	type="int"         ,	default=-1   ,				help="radius for PCA" )
	#parser.add_option("--iter", 		type="int"         ,	default=40   ,				help="maximum number of iterations (stop criterion of reconstruction process)" )
	#parser.add_option("--abs", 		type="float"   ,        default=0.0  ,				help="minimum average absolute change of voxels' values (stop criterion of reconstruction process)" )
	#parser.add_option("--squ", 		type="float"   ,	    default=0.0  ,				help="minimum average squared change of voxels' values (stop criterion of reconstruction process)" )
	parser.add_option("--VAR" , 		action="store_true",	default=False,				help="Stack of input consists of 2D variances (Default False)")
	parser.add_option("--decimate",     type="float",           default=0.25,               help="Image decimate rate, a number less than 1. (Default is 0.25)")
	parser.add_option("--window",       type="int",             default=0,                  help="Target image size relative to original image size. (Default value is zero.)")
	#parser.add_option("--SND",			action="store_true",	default=False,				help="compute squared normalized differences (Default False)")
	parser.add_option("--nvec",			type="int"         ,	default=0    ,				help="Number of eigenvectors, (Default = 0 meaning no PCA calculated)")
	parser.add_option("--symmetrize",	action="store_true",	default=False,				help="Prepare input stack for handling symmetry (Default False)")
	parser.add_option("--memory_per_node", type="float",        default=-1.0,               help="Available memory per node, (Default value is -1. Program will assign 2 GB for each CPU)")

	(options,args) = parser.parse_args()
	#####
	#from mpi import *

	#  This is code for handling symmetries by the above program.  To be incorporated. PAP 01/27/2015


	# Set up global variables related to bdb cache 
	if global_def.CACHE_DISABLE:
		sparx_utilities.disable_bdb_cache()
	
	# Set up global variables related to ERROR function
	global_def.BATCH = True
	
	# detect if program is running under MPI
	RUNNING_UNDER_MPI = "OMPI_COMM_WORLD_SIZE" in os.environ
	if RUNNING_UNDER_MPI: global_def.MPI = True
	
	if options.symmetrize :
		if RUNNING_UNDER_MPI:
			try:
				sys.argv = mpi.mpi_init(len(sys.argv), sys.argv)
				try:	
					number_of_proc = mpi.mpi_comm_size(mpi.MPI_COMM_WORLD)
					if( number_of_proc > 1 ):
						sparx_global_def.ERROR("Cannot use more than one CPU for symmetry prepration","sx3dvariability",1)
				except:
					pass
			except:
				pass
		if options.output_dir !="./" and not os.path.exists(options.output_dir): os.mkdir(options.output_dir)
		#  Input
		#instack = "Clean_NORM_CTF_start_wparams.hdf"
		#instack = "bdb:data"
		
		
		if os.path.exists(os.path.join(options.output_dir, "log.txt")): os.remove(os.path.join(options.output_dir, "log.txt"))
		log_main=sparx_logger.Logger(sparx_logger.BaseLogger_Files())
		log_main.prefix = os.path.join(options.output_dir, "./")
		
		instack = args[0]
		sym = options.sym.lower()
		if( sym == "c1" ):
			sparx_global_def.ERROR("There is no need to symmetrize stack for C1 symmetry","sx3dvariability",1)
		
		line =""
		for a in sys.argv:
			line +=" "+a
		log_main.add(line)
	
		if(instack[:4] !="bdb:"):
			if options.output_dir =="./": stack = "bdb:data"
			else: stack = "bdb:"+options.output_dir+"/data"
			sparx_utilities.delete_bdb(stack)
			junk = sparx_utilities.cmdexecute("sxcpy.py  "+instack+"  "+stack)
		else: stack = instack
		
		qt = EMAN2_cppwrap.EMUtil.get_all_attributes(stack,'xform.projection')

		na = len(qt)
		ts = sparx_utilities.get_symt(sym)
		ks = len(ts)
		angsa = [None]*na
		
		for k in range(ks):
			#Qfile = "Q%1d"%k
			if options.output_dir!="./": Qfile = os.path.join(options.output_dir,"Q%1d"%k)
			else: Qfile = os.path.join(options.output_dir, "Q%1d"%k)
			#delete_bdb("bdb:Q%1d"%k)
			sparx_utilities.delete_bdb("bdb:"+Qfile)
			#junk = cmdexecute("e2bdb.py  "+stack+"  --makevstack=bdb:Q%1d"%k)
			junk = sparx_utilities.cmdexecute("e2bdb.py  "+stack+"  --makevstack=bdb:"+Qfile)
			#DB = db_open_dict("bdb:Q%1d"%k)
			DB = EMAN2db.db_open_dict("bdb:"+Qfile)
			for i in range(na):
				ut = qt[i]*ts[k]
				DB.set_attr(i, "xform.projection", ut)
				#bt = ut.get_params("spider")
				#angsa[i] = [round(bt["phi"],3)%360.0, round(bt["theta"],3)%360.0, bt["psi"], -bt["tx"], -bt["ty"]]
			#write_text_row(angsa, 'ptsma%1d.txt'%k)
			#junk = cmdexecute("e2bdb.py  "+stack+"  --makevstack=bdb:Q%1d"%k)
			#junk = cmdexecute("sxheader.py  bdb:Q%1d  --params=xform.projection  --import=ptsma%1d.txt"%(k,k))
			DB.close()
		if options.output_dir =="./": sparx_utilities.delete_bdb("bdb:sdata")
		else: sparx_utilities.delete_bdb("bdb:" + options.output_dir + "/"+"sdata")
		#junk = cmdexecute("e2bdb.py . --makevstack=bdb:sdata --filt=Q")
		sdata = "bdb:"+options.output_dir+"/"+"sdata"
		print(sdata)
		junk = sparx_utilities.cmdexecute("e2bdb.py   " + options.output_dir +"  --makevstack="+sdata +" --filt=Q")
		#junk = cmdexecute("ls  EMAN2DB/sdata*")
		#a = get_im("bdb:sdata")
		a = sparx_utilities.get_im(sdata)
		a.set_attr("variabilitysymmetry",sym)
		#a.write_image("bdb:sdata")
		a.write_image(sdata)

	else:

		sys.argv       = mpi.mpi_init(len(sys.argv), sys.argv)
		myid           = mpi.mpi_comm_rank(mpi.MPI_COMM_WORLD)
		number_of_proc = mpi.mpi_comm_size(mpi.MPI_COMM_WORLD)
		main_node      = 0
		shared_comm  = mpi.mpi_comm_split_type(mpi.MPI_COMM_WORLD, mpi.MPI_COMM_TYPE_SHARED,  0, mpi.MPI_INFO_NULL)
		myid_on_node = mpi.mpi_comm_rank(shared_comm)
		no_of_processes_per_group = mpi.mpi_comm_size(shared_comm)
		masters_from_groups_vs_everything_else_comm = mpi.mpi_comm_split(mpi.MPI_COMM_WORLD, main_node == myid_on_node, myid_on_node)
		color, no_of_groups, balanced_processor_load_on_nodes = sparx_utilities.get_colors_and_subsets(main_node, mpi.MPI_COMM_WORLD, myid, \
		    shared_comm, myid_on_node, masters_from_groups_vs_everything_else_comm)
		overhead_loading = 1.0*no_of_processes_per_group
		memory_per_node  = options.memory_per_node
		if memory_per_node == -1.: memory_per_node = 2.*no_of_processes_per_group
		keepgoing = 1
		
		if len(args) == 1: stack = args[0]
		else:
			print(( "usage: " + usage))
			print(( "Please run '" + progname + " -h' for detailed options"))
			return 1

		t0 = time.time()	
		# obsolete flags
		options.MPI  = True
		options.nvec = 0
		options.radiuspca = -1
		options.iter = 40
		options.abs  = 0.0
		options.squ  = 0.0

		if options.fl > 0.0 and options.aa == 0.0:
			sparx_global_def.ERROR("Fall off has to be given for the low-pass filter", "sx3dvariability", 1, myid)
			
		#if options.VAR and options.SND:
		#	ERROR("Only one of var and SND can be set!", "sx3dvariability", myid)
			
		if options.VAR and (options.ave2D or options.ave3D or options.var2D): 
			sparx_global_def.ERROR("When VAR is set, the program cannot output ave2D, ave3D or var2D", "sx3dvariability", 1, myid)
			
		#if options.SND and (options.ave2D or options.ave3D):
		#	ERROR("When SND is set, the program cannot output ave2D or ave3D", "sx3dvariability", 1, myid)
		
		if options.nvec > 0 :
			sparx_global_def.ERROR("PCA option not implemented", "sx3dvariability", 1, myid)
			
		if options.nvec > 0 and options.ave3D == None:
			sparx_global_def.ERROR("When doing PCA analysis, one must set ave3D", "sx3dvariability", 1, myid)
		
		if options.decimate>1.0 or options.decimate<0.0:
			sparx_global_def.ERROR("Decimate rate should be a value between 0.0 and 1.0", "sx3dvariability", 1, myid)
		
		if options.window < 0.0:
			sparx_global_def.ERROR("Target window size should be always larger than zero", "sx3dvariability", 1, myid)
			
		if myid == main_node:
			img  = sparx_utilities.get_image(stack, 0)
			nx   = img.get_xsize()
			ny   = img.get_ysize()
			if(min(nx, ny) < options.window):   keepgoing = 0
		keepgoing = sparx_utilities.bcast_number_to_all(keepgoing, main_node, mpi.MPI_COMM_WORLD)
		if keepgoing == 0: sparx_global_def.ERROR("The target window size cannot be larger than the size of decimated image", "sx3dvariability", 1, myid)

		options.sym = options.sym.lower()
		 
		# if global_def.CACHE_DISABLE:
		# 	from utilities import disable_bdb_cache
		# 	disable_bdb_cache()
		# global_def.BATCH = True
		
		if myid == main_node:
			if options.output_dir !="./" and not os.path.exists(options.output_dir): os.mkdir(options.output_dir)
	
		img_per_grp = options.img_per_grp
		nvec        = options.nvec
		radiuspca   = options.radiuspca
		#if os.path.exists(os.path.join(options.output_dir, "log.txt")): os.remove(os.path.join(options.output_dir, "log.txt"))
		log_main=sparx_logger.Logger(sparx_logger.BaseLogger_Files())
		log_main.prefix = os.path.join(options.output_dir, "./")

		if myid == main_node:
			line = ""
			for a in sys.argv: line +=" "+a
			log_main.add(line)
			log_main.add("-------->>>Settings given by all options<<<-------")
			log_main.add("Symmetry             : %s"%options.sym)
			log_main.add("Input stack          : %s"%stack)
			log_main.add("Output_dir           : %s"%options.output_dir)
			
			if options.ave3D: log_main.add("Ave3d                : %s"%options.ave3D)
			if options.var3D: log_main.add("Var3d                : %s"%options.var3D)
			if options.ave2D: log_main.add("Ave2D                : %s"%options.ave2D)
			if options.var2D: log_main.add("Var2D                : %s"%options.var2D)
			if options.VAR:   log_main.add("VAR                  : True")
			else:             log_main.add("VAR                  : False")
			if options.CTF:   log_main.add("CTF correction       : True  ")
			else:             log_main.add("CTF correction       : False ")
			
			log_main.add("Image per group      : %5d"%options.img_per_grp)
			log_main.add("Image decimate rate  : %4.3f"%options.decimate)
			log_main.add("Low pass filter      : %4.3f"%options.fl)
			log_main.add("Current low pass filter is equivalent to cutoff frequency %4.3f for original image size"%round((options.fl*options.decimate),3))
			log_main.add("Window size          : %5d "%options.window)
			log_main.add("sx3dvariability begins")
	
		symbaselen = 0
		if myid == main_node:
			nima = EMAN2_cppwrap.EMUtil.get_image_count(stack)
			img  = sparx_utilities.get_image(stack)
			nx   = img.get_xsize()
			ny   = img.get_ysize()
			nnxo = nx
			nnyo = ny
			if options.sym != "c1" :
				imgdata = sparx_utilities.get_im(stack)
				try:
					i = imgdata.get_attr("variabilitysymmetry").lower()
					if(i != options.sym):
						sparx_global_def.ERROR("The symmetry provided does not agree with the symmetry of the input stack", "sx3dvariability", 1, myid)
				except:
					sparx_global_def.ERROR("Input stack is not prepared for symmetry, please follow instructions", "sx3dvariability", 1, myid)
				i = len(sparx_utilities.get_symt(options.sym))
				if((nima/i)*i != nima):
					sparx_global_def.ERROR("The length of the input stack is incorrect for symmetry processing", "sx3dvariability", 1, myid)
				symbaselen = nima/i
			else:  symbaselen = nima
		else:
			nima = 0
			nx = 0
			ny = 0
			nnxo = 0
			nnyo = 0
		nima    = sparx_utilities.bcast_number_to_all(nima)
		nx      = sparx_utilities.bcast_number_to_all(nx)
		ny      = sparx_utilities.bcast_number_to_all(ny)
		nnxo    = sparx_utilities.bcast_number_to_all(nnxo)
		nnyo    = sparx_utilities.bcast_number_to_all(nnyo)
		if options.window > max(nx, ny):
			sparx_global_def.ERROR("Window size is larger than the original image size", "sx3dvariability", 1)
		
		if options.decimate == 1.:
			if options.window !=0:
				nx = options.window
				ny = options.window
		else:
			if options.window == 0:
				nx = int(nx*options.decimate+0.5)
				ny = int(ny*options.decimate+0.5)
			else:
				nx = int(options.window*options.decimate+0.5)
				ny = nx
		symbaselen     = sparx_utilities.bcast_number_to_all(symbaselen)
		if myid == main_node:
			log_main.add("The targeted image size:    %5d"%nx)
			if nx !=sparx_fundamentals.smallprime(nx):
				log_main.add("The target image size does not consist of small prime numbers")
			else:
				log_main.add("The targeted image size consists of small prime numbers")
		if radiuspca == -1: radiuspca = nx/2-2
		if myid == main_node: log_main.add("%-70s:  %d\n"%("Number of projection", nima))
		img_begin, img_end = sparx_applications.MPI_start_end(nima, number_of_proc, myid)
		
		"""
		if options.SND:
		
			imgdata = EMData.read_images(stack, range(img_begin, img_end))

			if options.CTF:
				vol = recons3d_4nn_ctf_MPI(myid, imgdata, 1.0, symmetry=options.sym, npad=options.npad, xysize=-1, zsize=-1)
			else:
				vol = recons3d_4nn_MPI(myid, imgdata, symmetry=options.sym, npad=options.npad, xysize=-1, zsize=-1)

			bcast_EMData_to_all(vol, myid)
			volft, kb = prep_vol(vol)

			mask = model_circle(nx/2-2, nx, ny)
			varList = []
			for i in xrange(img_begin, img_end):
				phi, theta, psi, s2x, s2y = get_params_proj(imgdata[i-img_begin])
				ref_prj = prgs(volft, kb, [phi, theta, psi, -s2x, -s2y])
				if options.CTF:
					ctf_params = get_ctf(imgdata[i-img_begin])
					ref_prj = filt_ctf(ref_prj, generate_ctf(ctf_params))
				diff, A, B = im_diff(ref_prj, imgdata[i-img_begin], mask)
				diff2 = diff*diff
				set_params_proj(diff2, [phi, theta, psi, s2x, s2y])
				varList.append(diff2)
			mpi_barrier(MPI_COMM_WORLD)
		"""
		
		if options.VAR: # 2D variance images have no shifts
			varList   = EMAN2_cppwrap.EMData.read_images(stack, range(img_begin, img_end))
			if options.window > 0:
				mx = nnxo//2 - options.window//2
				my = nnyo//2 - options.window//2
				reg = EMAN2_cppwrap.Region(mx, my, options.window, options.window)
			else: reg = None
			for index_of_particle in range(img_begin,img_end):
				image = sparx_utilities.get_im(stack, index_of_particle)
				if reg: varList.append(sparx_fundamentals.subsample(image.get_clip(reg), options.decimate))
				else:   varList.append(sparx_fundamentals.subsample(image, options.decimate))
				
		else:
			if myid == main_node:
				t1          = time.time()
				proj_angles = []
				aveList     = []
				tab = EMAN2_cppwrap.EMUtil.get_all_attributes(stack, 'xform.projection')	
				for i in range(nima):
					t     = tab[i].get_params('spider')
					phi   = t['phi']
					theta = t['theta']
					psi   = t['psi']
					x     = theta
					if x > 90.0: x = 180.0 - x
					x = x*10000+psi
					proj_angles.append([x, t['phi'], t['theta'], t['psi'], i])
				t2 = time.time()
				log_main.add( "%-70s:  %d\n"%("Number of neighboring projections", img_per_grp))
				log_main.add("...... Finding neighboring projections\n")
				log_main.add( "Number of images per group: %d"%img_per_grp)
				log_main.add( "Now grouping projections")
				proj_angles.sort()
				proj_angles_list = np.full((nima, 4), 0.0, dtype=np.float32)	
				for i in range(nima):
					proj_angles_list[i][0] = proj_angles[i][1]
					proj_angles_list[i][1] = proj_angles[i][2]
					proj_angles_list[i][2] = proj_angles[i][3]
					proj_angles_list[i][3] = proj_angles[i][4]
			else: proj_angles_list = 0
			proj_angles_list = sparx_utilities.wrap_mpi_bcast(proj_angles_list, main_node, mpi.MPI_COMM_WORLD)
			proj_angles      = []
			for i in range(nima):
				proj_angles.append([proj_angles_list[i][0], proj_angles_list[i][1], proj_angles_list[i][2], int(proj_angles_list[i][3])])
			del proj_angles_list
			proj_list, mirror_list = sparx_utilities.nearest_proj(proj_angles, img_per_grp, range(img_begin, img_end))
			all_proj = sets.Set()
			for im in proj_list:
				for jm in im:
					all_proj.add(proj_angles[jm][3])
			all_proj = list(all_proj)
			index = {}
			for i in range(len(all_proj)): index[all_proj[i]] = i
			mpi.mpi_barrier(mpi.MPI_COMM_WORLD)
			if myid == main_node:
				log_main.add("%-70s:  %.2f\n"%("Finding neighboring projections lasted [s]", time.time()-t2))
				log_main.add("%-70s:  %d\n"%("Number of groups processed on the main node", len(proj_list)))
				log_main.add("Grouping projections took: ", (time.time()-t2)/60	, "[min]")
				log_main.add("Number of groups on main node: ", len(proj_list))
			mpi.mpi_barrier(mpi.MPI_COMM_WORLD)

			if myid == main_node:
				log_main.add("...... Calculating the stack of 2D variances \n")
				log_main.add("Now calculating the stack of 2D variances")
			# Memory estimation. There are two memory consumption peaks
			# peak 1. Compute ave, var; 
			# peak 2. Var volume reconstruction;
			# proj_params = [0.0]*(nima*5)
			aveList = []
			varList = []				
			if nvec > 0: eigList = [[] for i in range(nvec)]
			dnumber  = len(all_proj)# all neighborhood set for assigned to myid
			pnumber  = len(proj_list)*2. +img_per_grp # aveList and varList 
			tnumber  =   dnumber+pnumber
			vol_size2 =  nx**3*4.*8/1.e9
			vol_size1 =  2.*nnxo**3*4.*8/1.e9
			proj_size =  nnxo*nnyo*len(proj_list)*4.*2./1.e9 # both aveList and varList
			orig_data_size    = nnxo*nnyo*4.*tnumber/1.e9
			reduced_data_size = nx*nx*4.*tnumber/1.e9
			full_data = np.full((number_of_proc, 2), -1., dtype=np.float16)
			full_data[myid] = orig_data_size, reduced_data_size
			if myid != main_node: 
				sparx_utilities.wrap_mpi_send(full_data, main_node, mpi.MPI_COMM_WORLD)
			if myid == main_node:
				for iproc in range(number_of_proc):
					if iproc != main_node:
						dummy = sparx_utilities.wrap_mpi_recv(iproc, mpi.MPI_COMM_WORLD)
						full_data[np.where(dummy>-1)] = dummy[np.where(dummy>-1)]
				del dummy
			mpi.mpi_barrier(mpi.MPI_COMM_WORLD)
			full_data = sparx_utilities.wrap_mpi_bcast(full_data, main_node, mpi.MPI_COMM_WORLD)
			# find the CPU with heaviest load
			minindx = np.argsort(full_data, 0)
			heavy_load_myid = minindx[-1][1]
			if myid == main_node:
				log_main.add("Number of images computed on each CPU:")
				log_main.add("CPU    orig size     reduced size")
				msg =""
				mem_on_node_orig    = np.full(no_of_groups, 0.0, dtype=np.float16)
				mem_on_node_current = np.full(no_of_groups, 0.0, dtype=np.float16)
				for iproc in range(number_of_proc):
					msg += "%5d   %8.3f GB  %8.3f GB"%(iproc, full_data[iproc][0], full_data[iproc][1])+"; "
					if (iproc%3 == 2):
						log_main.add(msg)
						msg =""
					mem_on_node_orig[iproc//no_of_processes_per_group]    += full_data[iproc][0]
					mem_on_node_current[iproc//no_of_processes_per_group] += full_data[iproc][1]
				if number_of_proc%3 !=0:log_main.add(msg)
				try:
					mem_bytes = os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES')# e.g. 4015976448
					mem_gib   = mem_bytes/(1024.**3)
					log_main.add("Available memory information provided by the operating system: %5.1f GB"%mem_gib)
					if mem_gib >memory_per_node: memory_per_node = mem_gib
				except: 
					mem_gib= None
				log_main.add("Estimated memory to be used per node:")
				msg = ""
				run_with_current_setting = True
				for inode in range(no_of_groups):
					msg += "%5d   %8.3f GB  %8.3f GB"%(inode, mem_on_node_orig[inode], mem_on_node_current[inode])+";"
					if mem_on_node_current[inode] > (memory_per_node -   overhead_loading): run_with_current_setting = False
					if (inode%3 == 2):
						log_main.add(msg)
						msg =""
				if no_of_groups%3 !=0:log_main.add(msg)
				## Estimate maximum decimate ratio:
				mem_on_node_orig = np.divide(mem_on_node_orig,(memory_per_node - overhead_loading))
				max_decimate = 1./np.amax(mem_on_node_orig)
				max_decimate = numpy.sqrt(max_decimate)
				if max_decimate>1.0:log_main.add("Memory can afford 2D ave and var computation without image decimation")
				else:log_main.add("Memory can afford computation with the largest image decimate for 2D ave and var of %6.3f "%max_decimate)
				if not run_with_current_setting:
					log_main.add("Warning: memory might not afford the computation with the currently used image decimation")
				recons3d_decimate_ratio =(memory_per_node - overhead_loading)/\
				     ((vol_size1 + proj_size)*no_of_processes_per_group)
				if recons3d_decimate_ratio< 1.:
					log_main.add("Memory can afford var3D/ave3D reconstruction with image decimate %6.3f"%recons3d_decimate_ratio)
				else:
					log_main.add("Memory can afford var3D/ave3D reconstruction without image decimation") 
			del full_data
			if myid == main_node: del mem_on_node_orig, mem_on_node_current, minindx
			mpi.mpi_barrier(mpi.MPI_COMM_WORLD)
			if myid == heavy_load_myid:
				log_main.add("Begin reading and preprocessing images on processor. Wait... ")
				ttt = time.time()
			#imgdata = EMData.read_images(stack, all_proj)			
			imgdata = []
			#if myid==0: print(get_im(stack, 0).get_attr_dict())
			# Compute region
			if options.window > 0:
				mx  = nnxo//2 - options.window//2
				my  = nnyo//2 - options.window//2
				reg = EMAN2_cppwrap.Region(mx, my, options.window, options.window)
			else: reg = None
			for index_of_proj in range(len(all_proj)):
				image = sparx_utilities.get_im(stack, all_proj[index_of_proj])
				if options.decimate>0:
					ctf = image.get_attr("ctf")
					ctf.apix = ctf.apix/options.decimate
					image.set_attr("ctf", ctf)
				if reg: imgdata.append(sparx_fundamentals.subsample(image.get_clip(reg), options.decimate))
				else:   imgdata.append(sparx_fundamentals.subsample(image, options.decimate))
				if myid == heavy_load_myid and index_of_proj%100 ==0:
					log_main.add(" ...... %6.2f%% "%(index_of_proj/float(len(all_proj))*100.))
			if myid == heavy_load_myid:
				log_main.add("All_proj data reading and preprocessing cost %7.2f m"%((time.time()-ttt)/60.))
				log_main.add("Wait till reading jobs on all cpu done...")
			del image
			if reg: del reg
			mpi.mpi_barrier(mpi.MPI_COMM_WORLD)
			'''	
			imgdata2 = EMData.read_images(stack, range(img_begin, img_end))
			if options.fl > 0.0:
				for k in xrange(len(imgdata2)):
					imgdata2[k] = filt_tanl(imgdata2[k], options.fl, options.aa)
			if options.CTF:
				vol = recons3d_4nn_ctf_MPI(myid, imgdata2, 1.0, symmetry=options.sym, npad=options.npad, xysize=-1, zsize=-1)
			else:
				vol = recons3d_4nn_MPI(myid, imgdata2, symmetry=options.sym, npad=options.npad, xysize=-1, zsize=-1)
			if myid == main_node:
				vol.write_image("vol_ctf.hdf")
				print_msg("Writing to the disk volume reconstructed from averages as		:  %s\n"%("vol_ctf.hdf"))
			del vol, imgdata2
			mpi_barrier(MPI_COMM_WORLD)
			'''
			if not options.no_norm: 
				mask = sparx_utilities.model_circle(nx/2-2, nx, nx)
			nx2 = 2*nx
			ny2 = 2*ny
			mx1  = nx2//2 - nx//2
			my1  = ny2//2 - ny//2
			reg1 = EMAN2_cppwrap.Region(mx1, my1, nx, ny)
			if myid == heavy_load_myid:
				log_main.add("Start computing 2D aveList and varList. Wait...")
				ttt = time.time()
			for i in range(len(proj_list)):
				ki = proj_angles[proj_list[i][0]][3]
				if ki >= symbaselen:  continue
				mi = index[ki]
				dpar = EMAN2_cppwrap.Util.get_transform_params(imgdata[mi], "xform.projection", "spider")
				phiM, thetaM, psiM, s2xM, s2yM  = dpar["phi"],dpar["theta"],dpar["psi"],-dpar["tx"]*options.decimate,-dpar["ty"]*options.decimate
				grp_imgdata = []
				for j in range(img_per_grp):
					mj = index[proj_angles[proj_list[i][j]][3]]
					cpar = EMAN2_cppwrap.Util.get_transform_params(imgdata[mj], "xform.projection", "spider")
					alpha, sx, sy, mirror = params_3D_2D_NEW(cpar["phi"], cpar["theta"],cpar["psi"], -cpar["tx"]*options.decimate, -cpar["ty"]*options.decimate, mirror_list[i][j])
					if thetaM <= 90:
						if mirror == 0:  alpha, sx, sy, scale = sparx_utilities.compose_transform2(alpha, sx, sy, 1.0, phiM - cpar["phi"], 0.0, 0.0, 1.0)
						else:            alpha, sx, sy, scale = sparx_utilities.compose_transform2(alpha, sx, sy, 1.0, 180-(phiM - cpar["phi"]), 0.0, 0.0, 1.0)
					else:
						if mirror == 0:  alpha, sx, sy, scale = sparx_utilities.compose_transform2(alpha, sx, sy, 1.0, -(phiM- cpar["phi"]), 0.0, 0.0, 1.0)
						else:            alpha, sx, sy, scale = sparx_utilities.compose_transform2(alpha, sx, sy, 1.0, -(180-(phiM - cpar["phi"])), 0.0, 0.0, 1.0)
					imgdata[mj].set_attr("xform.align2d", EMAN2_cppwrap.Transform({"type":"2D","alpha":alpha,"tx":sx,"ty":sy,"mirror":mirror,"scale":1.0}))
					grp_imgdata.append(imgdata[mj])
				if not options.no_norm:
					for k in range(img_per_grp):
						ave, std, minn, maxx = EMAN2_cppwrap.Util.infomask(grp_imgdata[k], mask, False)
						grp_imgdata[k] -= ave
						grp_imgdata[k] /= std
				if options.fl > 0.0:
					if options.CTF:
						for k in range(img_per_grp):
							ctf = grp_imgdata[k].get_attr("ctf")
							cimage = sparx_fundamentals.fft(sparx_filter.filt_tanl(sparx_filter.filt_ctf(sparx_fundamentals.fft(sparx_utilities.pad(grp_imgdata[k], nx2, ny2, 1,0.0)),\
							    grp_imgdata[k].get_attr("ctf"), binary=1), options.fl, options.aa))
							grp_imgdata[k] = cimage.get_clip(reg1)							
					else:
						for k in range(img_per_grp):
							grp_imgdata[k] = sparx_filter.filt_tanl(grp_imgdata[k], options.fl, options.aa)
				else:
					if options.CTF:
						for k in range(img_per_grp):
							cimage = sparx_fundamentals.fft(sparx_filter.filt_ctf(sparx_fundamentals.fft(sparx_utilities.pad(grp_imgdata[k], nx2, ny2, 1,0.0)),\
							   grp_imgdata[k].get_attr("ctf"), binary=1))
							grp_imgdata[k] = cimage.get_clip(reg1)
				'''
				if i < 10 and myid == main_node:
					for k in xrange(10):
						grp_imgdata[k].write_image("grp%03d.hdf"%i, k)
				'''
				"""
				if myid == main_node and i==0:
					for pp in xrange(len(grp_imgdata)):
						grp_imgdata[pp].write_image("pp.hdf", pp)
				"""
				ave, grp_imgdata = sparx_applications.prepare_2d_forPCA(grp_imgdata)
				"""
				if myid == main_node and i==0:
					for pp in xrange(len(grp_imgdata)):
						grp_imgdata[pp].write_image("qq.hdf", pp)
				"""

				var = sparx_utilities.model_blank(nx,ny)
				for q in grp_imgdata:  EMAN2_cppwrap.Util.add_img2(var, q)
				EMAN2_cppwrap.Util.mul_scalar(var, 1.0/(len(grp_imgdata)-1))
				# Switch to std dev
				var = sparx_morphology.square_root(sparx_morphology.threshold(var))
				#if options.CTF:	ave, var = avgvar_ctf(grp_imgdata, mode="a")
				#else:	            ave, var = avgvar(grp_imgdata, mode="a")
				"""
				if myid == main_node:
					ave.write_image("avgv.hdf",i)
					var.write_image("varv.hdf",i)
				"""

				sparx_utilities.set_params_proj(ave, [phiM, thetaM, 0.0, 0.0, 0.0])
				sparx_utilities.set_params_proj(var, [phiM, thetaM, 0.0, 0.0, 0.0])

				aveList.append(ave)
				varList.append(var)

				if nvec > 0:
					eig = sparx_applications.pca(input_stacks=grp_imgdata, subavg="", mask_radius=radiuspca, nvec=nvec, incore=True, shuffle=False, genbuf=True)
					for k in range(nvec):
						sparx_utilities.set_params_proj(eig[k], [phiM, thetaM, 0.0, 0.0, 0.0])
						eigList[k].append(eig[k])
					"""
					if myid == 0 and i == 0:
						for k in xrange(nvec):
							eig[k].write_image("eig.hdf", k)
					"""
				if (myid == heavy_load_myid) and (i%100 == 0):
					log_main.add(" ......%6.2f%%  "%(i/float(len(proj_list))*100.))		
			del imgdata, grp_imgdata, cpar, dpar, all_proj, proj_angles, index, reg1
			if options.CTF: del cimage
			if not options.no_norm: del mask
			if myid == main_node: del tab
			#  To this point, all averages, variances, and eigenvectors are computed
			if (myid == heavy_load_myid):
				log_main.add("Computing aveList and varList cost %7.2f m"%((time.time()-ttt)/60.))
			mpi.mpi_barrier(mpi.MPI_COMM_WORLD) # synchronize all cpus
			if options.ave2D:
				if myid == main_node:
					log_main.add("Compute ave2D ... ")
					km = 0
					for i in range(number_of_proc):
						if i == main_node :
							for im in range(len(aveList)):
								aveList[im].write_image(os.path.join(options.output_dir, options.ave2D), km)
								km += 1
						else:
							nl = mpi.mpi_recv(1, mpi.MPI_INT, i, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)
							nl = int(nl[0])
							for im in range(nl):
								ave = sparx_utilities.recv_EMData(i, im+i+70000)
								"""
								nm = mpi_recv(1, MPI_INT, i, SPARX_MPI_TAG_UNIVERSAL, MPI_COMM_WORLD)
								nm = int(nm[0])
								members = mpi_recv(nm, MPI_INT, i, SPARX_MPI_TAG_UNIVERSAL, MPI_COMM_WORLD)
								ave.set_attr('members', map(int, members))
								members = mpi_recv(nm, MPI_FLOAT, i, SPARX_MPI_TAG_UNIVERSAL, MPI_COMM_WORLD)
								ave.set_attr('pix_err', map(float, members))
								members = mpi_recv(3, MPI_FLOAT, i, SPARX_MPI_TAG_UNIVERSAL, MPI_COMM_WORLD)
								ave.set_attr('refprojdir', map(float, members))
								"""
								tmpvol=sparx_fundamentals.fpol(ave, nx,nx,1)								
								tmpvol.write_image(os.path.join(options.output_dir, options.ave2D), km)
								km += 1
				else:
					mpi.mpi_send(len(aveList), 1, mpi.MPI_INT, main_node, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)
					for im in range(len(aveList)):
						sparx_utilities.send_EMData(aveList[im], main_node,im+myid+70000)
						"""
						members = aveList[im].get_attr('members')
						mpi_send(len(members), 1, MPI_INT, main_node, SPARX_MPI_TAG_UNIVERSAL, MPI_COMM_WORLD)
						mpi_send(members, len(members), MPI_INT, main_node, SPARX_MPI_TAG_UNIVERSAL, MPI_COMM_WORLD)
						members = aveList[im].get_attr('pix_err')
						mpi_send(members, len(members), MPI_FLOAT, main_node, SPARX_MPI_TAG_UNIVERSAL, MPI_COMM_WORLD)
						try:
							members = aveList[im].get_attr('refprojdir')
							mpi_send(members, 3, MPI_FLOAT, main_node, SPARX_MPI_TAG_UNIVERSAL, MPI_COMM_WORLD)
						except:
							mpi_send([-999.0,-999.0,-999.0], 3, MPI_FLOAT, main_node, SPARX_MPI_TAG_UNIVERSAL, MPI_COMM_WORLD)
						"""

			if options.ave3D:
				t5 = time.time()
				if myid == main_node: log_main.add("Reconstruct ave3D ... ")
				ave3D = sparx_reconstruction.recons3d_4nn_MPI(myid, aveList, symmetry=options.sym, npad=options.npad)
				sparx_utilities.bcast_EMData_to_all(ave3D, myid)
				if myid == main_node:
					if options.decimate != 1.0: ave3D = sparx_fundamentals.resample(ave3D, 1./options.decimate)
					ave3D = sparx_fundamentals.fpol(ave3D, nnxo, nnxo, nnxo) # always to the orignal image size
					sparx_utilities.set_pixel_size(ave3D, 1.0)
					ave3D.write_image(os.path.join(options.output_dir, options.ave3D))
					log_main.add("%-70s:  %.2f\n"%("Ave3D reconstruction took [s]", time.time()-t5))
					log_main.add("%-70s:  %s\n"%("The reconstructed ave3D is saved as ", options.ave3D))
					
			mpi.mpi_barrier(mpi.MPI_COMM_WORLD)		
			del ave, var, proj_list, stack, alpha, sx, sy, mirror, aveList
			if nvec > 0:
				for k in range(nvec):
					if myid == main_node:log_main.add("Reconstruction eigenvolumes", k)
					cont = True
					ITER = 0
					mask2d = sparx_utilities.model_circle(radiuspca, nx, nx)
					while cont:
						#print "On node %d, iteration %d"%(myid, ITER)
						eig3D = sparx_reconstruction.recons3d_4nn_MPI(myid, eigList[k], symmetry=options.sym, npad=options.npad)
						sparx_utilities.bcast_EMData_to_all(eig3D, myid, main_node)
						if options.fl > 0.0:
							eig3D = sparx_filter.filt_tanl(eig3D, options.fl, options.aa)
						if myid == main_node:
							eig3D.write_image(os.path.join(options.outpout_dir, "eig3d_%03d.hdf"%(k, ITER)))
						EMAN2_cppwrap.Util.mul_img( eig3D, sparx_utilities.model_circle(radiuspca, nx, nx, nx) )
						eig3Df, kb = sparx_projection.prep_vol(eig3D)
						del eig3D
						cont = False
						icont = 0
						for l in range(len(eigList[k])):
							phi, theta, psi, s2x, s2y = sparx_utilities.get_params_proj(eigList[k][l])
							proj = sparx_projection.prgs(eig3Df, kb, [phi, theta, psi, s2x, s2y])
							cl = sparx_statistics.ccc(proj, eigList[k][l], mask2d)
							if cl < 0.0:
								icont += 1
								cont = True
								eigList[k][l] *= -1.0
						u = int(cont)
						u = mpi.mpi_reduce([u], 1, mpi.MPI_INT, mpi.MPI_MAX, main_node, mpi.MPI_COMM_WORLD)
						icont = mpi.mpi_reduce([icont], 1, mpi.MPI_INT, mpi.MPI_SUM, main_node, mpi.MPI_COMM_WORLD)

						if myid == main_node:
							u = int(u[0])
							log_main.add(" Eigenvector: ",k," number changed ",int(icont[0]))
						else: u = 0
						u = sparx_utilities.bcast_number_to_all(u, main_node)
						cont = bool(u)
						ITER += 1

					del eig3Df, kb
					mpi.mpi_barrier(mpi.MPI_COMM_WORLD)
				del eigList, mask2d

			if options.ave3D: del ave3D
			if options.var2D:
				if myid == main_node:
					log_main.add("Compute var2D...")
					km = 0
					for i in range(number_of_proc):
						if i == main_node :
							for im in range(len(varList)):
								tmpvol=sparx_fundamentals.fpol(varList[im], nx, nx,1)
								tmpvol.write_image(os.path.join(options.output_dir, options.var2D), km)
								km += 1
						else:
							nl = mpi.mpi_recv(1, mpi.MPI_INT, i, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)
							nl = int(nl[0])
							for im in range(nl):
								ave = sparx_utilities.recv_EMData(i, im+i+70000)
								tmpvol=sparx_fundamentals.fpol(ave, nx, nx,1)
								tmpvol.write_image(os.path.join(options.output_dir, options.var2D), km)
								km += 1
				else:
					mpi.mpi_send(len(varList), 1, mpi.MPI_INT, main_node, sparx_global_def.SPARX_MPI_TAG_UNIVERSAL, mpi.MPI_COMM_WORLD)
					for im in range(len(varList)):
						sparx_utilities.send_EMData(varList[im], main_node, im+myid+70000)#  What with the attributes??
			mpi.mpi_barrier(mpi.MPI_COMM_WORLD)

		if options.var3D:
			if myid == main_node: log_main.add("Reconstruct var3D ...")
			t6 = time.time()
			# radiusvar = options.radius
			# if( radiusvar < 0 ):  radiusvar = nx//2 -3
			res = sparx_reconstruction.recons3d_4nn_MPI(myid, varList, symmetry = options.sym, npad=options.npad)
			#res = recons3d_em_MPI(varList, vol_stack, options.iter, radiusvar, options.abs, True, options.sym, options.squ)
			if myid == main_node:
				if options.decimate != 1.0: res	= sparx_fundamentals.resample(res, 1./options.decimate)
				res = sparx_fundamentals.fpol(res, nnxo, nnxo, nnxo)
				sparx_utilities.set_pixel_size(res, 1.0)
				res.write_image(os.path.join(options.output_dir, options.var3D))
				log_main.add("%-70s:  %s\n"%("The reconstructed var3D is saved as ", options.var3D))
				log_main.add("%-70s:  %.2f\n"%("Var3D reconstruction took [s]", time.time()-t6))
				log_main.add("%-70s:  %.2f\n"%("Total computation time [m]", (time.time()-t0)/60.))
				log_main.add("sx3dvariability finishes")
		mpi.mpi_finalize()
		
		if RUNNING_UNDER_MPI: global_def.MPI = False

		global_def.BATCH = False

if __name__=="__main__":
	main()

