

import os
import pprint
from tracker import *
#from oracle import Oracle

import shutil
def SplitFile(filename, *chunkinfo, chunksize = 10**6):
	'''
	chunkinfo is a list of tuples of the form (subfilename, subfilesize)
	the length of all the chunks should add up to the size of filename
	'''

	with open(filename, 'rb') as f:
		for i in chunkinfo:
			with open(i[0], 'wb') as sf:
				length = i[1]
				num_chunks = i[1] // (chunksize)   # Write in 1 Meg chunks
				rem = i[1] % (chunksize)
				for i in range(num_chunks):
					sf.write(f.read(chunksize))
				sf.write(f.read(rem))
				sf.truncate()

	os.remove(filename)

	os.makedirs(filename)
	for i in chunkinfo:
		shutil.move(i[0], os.path.join(filename, i[0]))


