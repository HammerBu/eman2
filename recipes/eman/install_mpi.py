#!/usr/bin/env python

from optparse import OptionParser
import os
from sys import exit


def myexec(cmd):
	print  "	 ", cmd
	r = os.system(cmd)
	if r != 0:
		print "Command execution failed!"
		print "If it failed at wget or curl due to no Internet connection, try download the file from other machine,",
		print "copy it to the current directory and restart install_mpi.py.",
		print "Otherwise, check the log file and try to resolve it."
		sys.exit(-1)

def chdir(dir):
	print  "	  cd ", dir
	os.chdir(dir)

def get_mpiroot(options):
	print "Checking mpicc"
		
	r = os.system("mpicc --version")
	if r != 0:
		print "Cannot find mpicc"
		return False
		
	return True
	
def update_Makefile_src():
	pwd = os.getcwd()
	chdir("src")

	prefix_location = os.environ['PREFIX']
	adding_dict = {
		"CFLAGS = " : ' -I%s/include -DPYDUSA_VERSION=%s'  %(prefix_location, pwd),
		"LDFLAGS = " : " -L%s/lib -lfftw3_mpi -lfftw3 -lm "%(prefix_location)
	}

	statbuf = os.stat("Makefile")

	move_to_original = True
	with open("Makefile", "r") as fp, open("Makefile___out", "w") as fp_out:
		for line in fp:
			for key in adding_dict:
				if line[:len(key)] == key:
					if adding_dict[key] not in line:
						fp_out.write(line[:-1])
						fp_out.write(adding_dict[key])
						fp_out.write("\n")
					else:
						fp_out.write(line)
						move_to_original = False
					break
			else:
				fp_out.write(line)
				
	if move_to_original:
		myexec("mv Makefile Makefile___original")
		myexec("mv Makefile___out Makefile")

	os.utime("Makefile",(statbuf.st_atime,statbuf.st_mtime))

	os.chdir(pwd)
	

default_version_of_open_mpi_to_istall = "1.10.2"

parser = OptionParser()
parser.add_option("--openmpi_ver", type="string",  default=default_version_of_open_mpi_to_istall, help="version of openmpi to forcefully install, default = %s"%default_version_of_open_mpi_to_istall)
options,args = parser.parse_args()

if not get_mpiroot(options):
	print "You need MPI environment (both runtime and developer packages) and gcc compiler to continue. "
	print "If you work on professional HPC cluster, in all likelihood both are already installed. "
	print "In this case read the user guide - you have to probably load appriopriate module by \"module load\" command."
	print "You can also run this script again with the --force option - it will download and install MPI (openmpi-%s) for you."%default_version_of_open_mpi_to_istall
	exit(-1)

print ""
print "=====> Configuring the mpi python binding"

myexec("./configure --prefix=%s" % os.environ['SP_DIR'])

##  need to update the Makefile in src to include the -I and -L for fftw-mpi compilation
update_Makefile_src()
		
print ""
print "=====> Building the mpi python binding"
myexec("make clean >> log.txt")	
myexec("make all >> log.txt")


print ""
print "=====> Install the mpi python binding"
myexec("make install >> log.txt")	
