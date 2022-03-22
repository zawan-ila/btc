import os
import functools
import hashlib
import time
import threading
from util import SplitFile
import sys
import signal

from tracker import *
from peers import *

NUM_PEERS = 10
BLOCK_SIZE = 2**14
UNREQUESTED = 0
REQUESTED = 1
DONE = 2

class Oracle:
	"""
	This is the Oracle. 

	It manages the creation of a number of peer
	connections and doling out block requests to these connections 
	and receiving blocks from these connections
	"""

	"""
	Make a tracker object
	Get List of Peers
	Contact tracker periodically or when run out of peers?
	Make a number of peer connections
	Pass the list of peers to each connection
	Each connection will connect to a peer
	
	"""

	def __init__(self, torr_info):



		self.tracker = Tracker(torr_info)
		self.PeerQueue = queue.Queue()

		self.Hashes = self.tracker.GetHashes() # Hashes for all the pieces in order

		self.pieces = [Piece(i, self.tracker.PieceLen, self.Hashes[i], status = UNREQUESTED) for i in range(self.tracker.NumPieces)]

		# Last piece may have different length
		if self.tracker.TorrLen % self.tracker.PieceLen:

			p = self.pieces[-1]
			p.length = self.tracker.TorrLen % self.tracker.PieceLen
			p.__init__(p.PieceIdx, p.length, p.hash)



		self.completed = 0	#Number of Pieces retrieved

		self.lock = threading.Lock()

		self.peer_bitfields = {} # Dict storing the pieces each peer has
		self.peer_pieces = {} # Dict storing pieces being processed by each peer
		self.filename = self.tracker.filename
		with open(self.filename, 'a'):
			pass
		self.PieceLen = self.tracker.PieceLen
		self.curr_idx = 0

		signal.signal(signal.SIGINT, self.SigHandle)

		self.TryResume()

	
	def start(self):
		"""
		This is the main loop
		Create Threads for each peer connection
		"""
		epoch = time.time()

		# Create threads here
		kids = [threading.Thread(target = Peer(self.lock, self.tracker.info_hash, self.PeerQueue, self,
				i).Start,
				daemon = True) for i in range(NUM_PEERS)] #debug, arbitrary id in place of trackr id

		for j in kids:
			j.start()	 

		start_time = time.time()
		counter = 0
		while True:
			if self.completed == len(self.pieces):

				print('COMPLETED IN {} MINUTES'.format((time.time() - epoch)/60))

				if self.tracker.multifileinfo:
					SplitFile(self.filename, *self.tracker.multifileinfo)
					
				# Done?
				# File has been completely downloaded?
				break

			if (time.time() > (start_time + self.tracker.reconnect_time)) or (self.PeerQueue.qsize() == 0):
				#Reconnect to tracker ?
				#Get new list of peers?
				#Update PeerQueue
				#update start_time
				dwnldd = (self.completed)*self.PieceLen
				pq = self.tracker.GetPeers(dwnldd, self.tracker.TorrLen - dwnldd, 0)
				if pq:
					for i in pq:
						self.PeerQueue.put(i)

					start_time = time.time()
				else:
					pass
 

	def CreateBitfield(self, peeraddr, bitfield):

		if peeraddr in self.peer_bitfields:
			return None
		self.peer_bitfields[peeraddr] = bytearray(bitfield)
		return bitfield

	def UpdateBitfield(self, peeraddr, pieceidx):

		if peeraddr in self.peer_bitfields:
			pass
		else:
			b = len(self.pieces) // 8
			if len(self.pieces) % 8:
				b += 1
			self.peer_bitfields[peeraddr] = bytearray(b)

		self.peer_bitfields[peeraddr][(pieceidx//8)]  |= (128 >> (pieceidx % 8))
		return self.peer_bitfields[peeraddr]

	def GetNewBlock(self, peeraddr, id):
		if peeraddr in self.peer_pieces:
			pc = self.peer_pieces[peeraddr]
			block = pc.GetNextBlock()
			if block is not None:
				return block

			# pc is complete?
			elif pc.VerifyPiece():
				

				self.WritePiece(pc, id)
				pc.status = DONE
				pc.Destroy()
				del self.peer_pieces[peeraddr]
				# self.completed += 1

			else:
				pc.__init__(pc.PieceIdx, pc.length, pc.hash)
				del self.peer_pieces[peeraddr]

		for i in range(len(self.pieces)):
			if self.pieces[self.curr_idx].status == UNREQUESTED and self.PeerHas(peeraddr, self.pieces[self.curr_idx]):
				self.pieces[self.curr_idx].status = REQUESTED #?
				self.peer_pieces[peeraddr] = self.pieces[self.curr_idx]
				blk = self.pieces[self.curr_idx].GetNextBlock()
				blk.status = REQUESTED
				return blk
			else:
				self.curr_idx = (self.curr_idx + 1) % len(self.pieces)

		for i in self.pieces:
			if i.status == REQUESTED and self.PeerHas(peeraddr, i):
				self.peer_pieces[peeraddr] = i
				blk = i.GetNextBlock()

				if blk:
					blk.status = REQUESTED
					return blk

		# NO Block available
		# Calling connection should try to change peer
		return None

	def ReceiveBlock(self, datum, blk):
		blk.data = datum
		blk.status = DONE


	def PeerHas(self,peeraddr, i):
		try:
			idx = i.PieceIdx
			bf = self.peer_bitfields[peeraddr]

			if bf[idx//8] & (128>>(idx%8)):
				return True
			else:
				return False
		except KeyError as err:
			return False


	def RemovePeer(self,peeraddr):
		try:
			del self.peer_bitfields[peeraddr]
		except KeyError:
			pass

		try:
			del self.peer_pieces[peeraddr]
		except KeyError:
			pass

	def WritePiece(self, pieceobj, id):
		idx = pieceobj.PieceIdx

		if pieceobj.status != DONE:
			data = pieceobj.Data()
			with open(self.filename, "rb+") as gosh:
				gosh.seek(idx * self.PieceLen)
				gosh.write(data)

			self.completed += 1
			print("{} / {} pieces downloaded".format(self.completed, len(self.pieces)))


	def TryResume(self):
		try:
			sz = os.path.getsize(self.filename)
		except OSError:
			'''
			File does not exist

			'''
			print('Non Existent Earlier Pieces')
			return

		f = open(self.filename, 'rb')
		numAlreadyIntact = 0

		for i in self.pieces:
			if (i.PieceIdx*self.PieceLen + i.length) <= sz:
				f.seek(i.PieceIdx*self.PieceLen)
				data = f.read(i.length)

				if hashlib.sha1(data).digest() == i.hash:
					i.status = DONE
					numAlreadyIntact += 1
			else:
				break
		f.close()

		print(numAlreadyIntact, 'pieces already available', 'out of', len(self.pieces))
		self.completed += numAlreadyIntact


	def SigHandle(self, sig, stack):
		print('Quitting...')
		print('GoodBye')
		sys.exit()


class Block:



	def __init__(self,PieceNum, offset, length, status = UNREQUESTED, data = b''):
		self.PieceNum = PieceNum
		self.offset = offset
		self.length = length
		self.status = status
		self.data = data

class Piece:
	
	def __init__(self, PieceNum, PieceLen, PieceHash, status = UNREQUESTED):
		self.PieceIdx = PieceNum
		self.length = PieceLen
		self.hash = PieceHash
		self.blocks = self.MakeBlocks()
		self.status = status   
		self.curr_idx = 0

	def MakeBlocks(self):
		blocks = [Block(self.PieceIdx, ofst, BLOCK_SIZE) for ofst in range(0, self.length, BLOCK_SIZE)]
		if (self.length % BLOCK_SIZE):
			blocks[-1].length = self.length % BLOCK_SIZE

		return blocks


	def VerifyPiece(self):
		"""
		Verify the SHA1 hash of the piece and return the piece data
		so that it can be written to disk
		"""

		if self.status == DONE:
			return True
		h = hashlib.sha1(self.Data()).digest()
		return h == self.hash


	def Data(self):
		self.blocks = sorted(self.blocks,key = lambda j: j.offset) 
		data = [i.data for i in self.blocks]
		data = functools.reduce(lambda a,b: a+b, data)
		return data

	def GetNextBlock(self):
		for i in range(len(self.blocks)):
			if self.blocks[self.curr_idx].status == UNREQUESTED:
				self.blocks[self.curr_idx].status = REQUESTED
				return self.blocks[self.curr_idx]
			else:
				self.curr_idx = (self.curr_idx + 1) % len(self.blocks)

		# No unrequested blocks ?
		# Maybe retry a requested block ?

		for i in self.blocks:
			if i.status == REQUESTED:
				return i

		# No Pending blocks either?
		# Piece is Complete ? 

		return None


	def Destroy(self):
		'''
		Does this really free memory?
		'''
		for i in self.blocks:
			i.data = None









	











	









