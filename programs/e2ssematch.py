#!/usr/bin/env python
# ssematch.py  08/28/2006  Steven Ludtke, Matt Baker
# This tries to match sequence based secondary structure prediction to
# ssehunter results, based on length and distance constraints in each case

from EMAN2 import *
from optparse import OptionParser
from math import *
import time
import os
import sys

pl=()

def main():
	progname = os.path.basename(sys.argv[0])
	usage = """%prog [options] <ssehunter_file> <sec_struct_file>
	
ssehunter file is in ??? format
sec_struct_file is a string of -,H,E defining per-residue predicted structure"""

	parser = OptionParser(usage=usage,version=EMANVERSION)

#	parser.add_option("--gui",action="store_true",help="Start the GUI for interactive boxing",default=False)
#	parser.add_option("--auto","-A",type="string",action="append",help="Autobox using specified method: circle, ref, grid",default=[])
#	parser.add_option("--threshold","-T",type="float",help="Threshold for keeping particles. 0-4, 0 excludes all, 4 keeps all.",default=2.0)
	parser.add_option("--maxbad","-M",type="int",help="Maximumum number of unassigned helices",default=2)
	parser.add_option("--minhelix","-H",type="int",help="Minimum residues in a helix",default=6)
	parser.add_option("--maxpairerr","-E",type="float",help="Maximum error match between pairs of helices, default=50",default=50.0)
	
	(options, args) = parser.parse_args()
	if len(args)<1 : parser.error("Input image required")

	logid=E2init(sys.argv)
	
	ssematch(args[0],args[1],options)
	
def ssematch(ssehfsp,sspredfsp,options):
	"actual function of the program implemented here"
	
	sseh=readsseh(ssehfsp)
	sspred=readsspred(sspredfsp,options.minhelix)
	
	print "%d predicted helices    %d helices in density"%(len(sspred),len(sseh[0]))
	for i in sspred: print "%4d "%int(i[0]/1.5),
	print ""
	
	# get lists of possible pairwise assignments and quality assessment for each
	pairqual={}
	for i in range(len(sspred)-1):
		pairqual[i]=findpairs(i,sspred,sseh,options.maxpairerr)
		print "%4d "%len(pairqual[i]),
	print
	
	# This is where we generate all of the final answers
	all=[]
	recursesoln(pairqual,[],[],all,options.maxbad)
	
	out=file("ssematch.out","w")
	for i in all:
		out.write("%f\t%s\n"%(i[0],str(i[1])))
	out.close()
	
	print len(all)

def recursesoln(pairqual,tot,soln,all,maxbad):
	# first round, try all 1st level pairs
	if len(soln)==0 :
		for j,i in enumerate(pairqual[0]): 
			recursesoln(pairqual,[i[0]],[i[1],i[2]],all,maxbad)
			print "%d/%d"%(j,len(pairqual[0]))
		return
		
	# if we get here, we're done
	if len(soln)==len(pairqual):
		v=sum(tot)/len(tot)
		try:
			if v<min(all)[0]: print v,soln
		except: print v,soln
		all.append((v,soln))
		return
	
	tries=0
	for i in pairqual[len(soln)-1]:
		# three tests. If the previous element isn't undefined, it must match
		# and, the next choice in the series must not already be used
		if (soln[-1]!=-1 and i[1]!=soln[-1]) or i[2] in soln : continue		# next one in series already assigned
		tries+=1
		try: minq=min(minq,i[0])
		except: minq=i[0]
		recursesoln(pairqual,tot+[i[0]],soln+[i[2]],all,maxbad)
	
	# if we didn't find even one good assignment, we skip this helix (unless we've skipped too many)
	if (tries==0 or minq>32) and soln.count(-1)<maxbad:
		recursesoln(pairqual,tot,soln+[-1],all,maxbad)
	
def findpairs(p1,sspred,sseh,maxpe):
	"""This will generate a sorted list of possible pair assignments. Assigns the
	predicted helices p1 and p2 to two helices from sseh. Returns a sorted list of:
	(error,s1,s2)		lower error is a better match """
	
	ssemin=sseh[1]
	
	poss=[]
	for s1 in range(len(sseh[0])):
		for s2 in range(len(sseh[0])):
#			print ssemin[s1][s2][1],sspred[p1+1][1]
			if s1==s2 or ssemin[s1][s2][1]>sspred[p1+1][1]: continue
			# error includes squared length mismatches and a term downweighting long distances between helices
			err=(sspred[p1][0]-sseh[0][s1])**2+(sspred[p1+1][0]-sseh[0][s2])**2
			if ssemin[s1][s2][1]/sspred[p1+1][1]>.5: err+=(16.0*(ssemin[s1][s2][1]/sspred[p1+1][1]-.5))**2		# varies from 1-4
			poss.append((err,s1,s2))
	poss.sort()
	for i,v in enumerate(poss):
		if v[0]>maxpe : break
	if i==0: i+=1
	return poss[:i]
	
def readsseh(fsp):
	"""reads a ssehunter output file, returns 3 results:
	a list of helix lengths
	a distance matrix (h1,h2):(1|2,1|2,dist)  h1<h2
	
	This should really use skeletonization results to generate the distance
	matrix based on only connected h1,h2 pairs"""
	
	# this makes a list of all lines starting with ALPHA
	lns=[i for i in file(fsp,"r").readlines() if i[:5]=="ALPHA"]
	
	# this makes a vector of 6 floats (x0,y0,z0,x1,y1,z1) for each line
	hlx=[[float(j) for j in i.split()[5:]] for i in lns]
	
	# list of lengths of each helix
	lenlist=[sqrt((i[0]-i[3])**2+(i[1]-i[4])**2+(i[2]-i[5])**2) for i in hlx]
	
	# min length matrix (this needs to be replaced with connectivity info from skeletonization)
	# (h1,h2):((0|1,0|1),len)
	lenmx=[[[] for i in range(len(hlx))] for i in range(len(hlx))]
	for h1 in range(len(hlx)):
		for h2 in range(len(hlx)):
			if h1>=h2 : continue
			k=[(0,0),(0,1),(1,0),(1,1)]
			for i in k:
				l=sqrt((hlx[h1][i[0]*3]-hlx[h2][i[1]*3])**2+(hlx[h1][i[0]*3+1]-hlx[h2][i[1]*3+1])**2+(hlx[h1][i[0]*3+2]-hlx[h2][i[1]*3+2])**2)
				try: 
					if l<lenmx[h1][h2][1] : 
						lenmx[h1][h2]=(i,l)
						lenmx[h2][h1]=(i,l)
				except: 
						lenmx[h1][h2]=(i,l)
						lenmx[h2][h1]=(i,l)
	
	return (lenlist,lenmx)
					

def readsspred(fsp,minhelix):
	"""reads a file containing a sequence of -,H,E characters, 1 per residue.
	strips out extraneous whitespace. Produces an ordered list of helix lengths and the maximum distance
	to the previous helix 
	Probably should have a better measure of probable distance vs # residues."""
	seq=file(fsp,"r").read()
	
	# slow, but doesn't matter much here
	seq="".join([i for i in seq if i in ("H","E","-")])
	
	# construct the list by counting H and not H letter sequences
	lenlist=[]
	inh=0
	h1=0
	for i,l in enumerate(seq):
		if inh:
			if l!="H":
				if i-h0<minhelix:
					inh=0
					continue
				lenlist.append((1.5*(i-h0),3.8*(h0-h1)))
				h1=i-1
				inh=0
		else:
			if l=="H":
				h0=i
				inh=1

	return lenlist

if __name__ == "__main__":
	main()
