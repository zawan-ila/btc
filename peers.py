import pprint
import socket
import secrets
import re
import pprint
import hashlib
import time

from tracker import *
from oracle import *
UNREQUESTED = 0
REQUESTED = 1
DONE = 2

class Peer:
    def __init__(self, mtx, hash, PeerQueue, orcl, id) -> None:
        self.peerid = id
        self.lock = mtx
        self.choked = 1
        self.interested = 0
        self.peer_choked = 1
        self.peer_interested = 0
        self.info_hash = hash
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.buffer = b''   
        self.peerqueue = PeerQueue
        self.oracle = orcl
        self.in_progress = None

    def reset(self):
        self.choked = 1
        self.interested = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.buffer = b''
        self.in_progress = None


    def Start(self):
        self.sock.settimeout(30) # 30 seconds timeout?

        while True:         

            
            self.addr = self.peerqueue.get()


            if self.ConnectionSetup(self.addr):
                try:
                    # Handshake has been verified
                    self.sock.sendall(self.Make('Interested'))

                    max_try = 0
                    while self.choked and max_try < 10:
                        inc = self.ReadMessage()
                        if inc:
                            self.ParseResponse(*inc)


                        max_try += 1
                        #time.sleep(0.5)

                    if self.choked:
                        raise ValueError('Self.choked still 1')

                    # Now we are unchoked

                    
                    while True:
                        # Get Blocks from oracle and just fetch them
                        
                        with self.lock:
                            blk = self.oracle.GetNewBlock(self.addr, self.peerid)
                        if blk:
                            self.in_progress = blk
                            self.sock.sendall(self.Make('Request', blk.PieceNum, blk.offset, blk.length))
                            tries = 0
                            while True:
                                rsp = self.ReadMessage()
                                if rsp:
                                    self.ParseResponse(rsp[0], rsp[1])
                                    if rsp[0] == 7:
                                        break

                                elif tries > 3:
                                    raise AssertionError('Should a received block by now')

                                tries += 1

                        else:
                            # No Blocks for us? 
                            # This peer can't service us anymore?
                            with self.lock:
                                self.oracle.RemovePeer(self.addr)
                            self.reset() # Reinitialize this object?
                            self.Start() # Start again?
                    
                except (ValueError, socket.error, AssertionError) as e:
                    with self.lock:
                        self.oracle.RemovePeer(self.addr)
                    self.reset()
                    self.Start()




    def Make(self, kind, *args):

        if kind == 'Handshake':

            pstrlen = IntToBytes(19, 1)
            pstr = b'BitTorrent protocol'
            res = b'\x00'*8
            handshake_msg = pstrlen + pstr + res + self.info_hash + IntToBytes(self.peerid,20)

            return handshake_msg

        elif kind == 'KeepAlive':
            return IntToBytes(0)

        elif kind == 'Choke':
            return IntToBytes(1) + IntToBytes(0,1)

        elif kind == 'Unchoke':
            return IntToBytes(1) + IntToBytes(1,1)

        elif kind == 'Interested':
            return IntToBytes(1) + IntToBytes(2,1)

        elif kind == 'Uninterested':
            return IntToBytes(1) + IntToBytes(3,1)

        # The two cases below assume args to look like (piecenum, offset, length)

        elif kind == 'Request':
            return IntToBytes(13) + IntToBytes(6, 1) + IntToBytes(args[0]) + IntToBytes(args[1]) + IntToBytes(args[2])

        elif kind == 'Cancel':
            return IntToBytes(13) + IntToBytes(8, 1) + IntToBytes(args[0]) + IntToBytes(args[1]) + IntToBytes(args[2])

        else:
            # Shouldn't reach here
            pass

    def ParseResponse(self, msg_id, msg_contents):
        if msg_id == 0:
            self.choked = 1
        elif msg_id == 1:
            self.choked = 0

        elif msg_id == 4:
            with self.lock:
                self.oracle.UpdateBitfield(self.addr, BytesToInt(msg_contents))

        elif msg_id == 5:
            with self.lock:
                self.oracle.CreateBitfield(self.addr, msg_contents)

        elif msg_id ==7:

            data = msg_contents[8:]
            with self.lock:
                self.oracle.ReceiveBlock(data, self.in_progress)


        else:
            '''
            Ignore cancel, interested, not-interested, cancel messages
            '''
            pass
        
    




    def ReadMessage(self):

        """
        Reads a full message from the socket
        Buffers any excess bytes read for later use (future calls)
        """

        try:

            while len(self.buffer) < 4:
                incomin = self.sock.recv(1024)
                self.buffer += incomin
                if incomin == b'':
                    raise socket.error('Connection just opened and Closed {}'.format(self.peerid))

        

            msglen = BytesToInt(self.buffer[0:4])

            while len(self.buffer) < 4 + msglen:
                incomin = self.sock.recv(1024)
                self.buffer += incomin
                if incomin == b'':
                    raise socket.error('Connection just opened and Closed {}'.format(self.peerid))


            '''
            Now we have at least one complete message in the buffer
            '''

            if msglen == 0:
                '''
                This is a KeepAliveMessage?
                Ignore It?
                '''

                self.strip(4)

                return None

            elif msglen >=  1:

                msg_id = (self.buffer[4])
                msg_contents = self.buffer[5:5 + msglen - 1]
                self.strip(msglen + 4)

                return msg_id, msg_contents
        except socket.error as e:
            return None

    def strip(self, numBytes):
        self.buffer = self.buffer[numBytes:]


    def ConnectionSetup(self, peeraddr):
        try:
            self.sock.settimeout(15)
            self.sock.connect(peeraddr)
            self.sock.sendall(self.Make("Handshake"))
            rcvd = b''
            while len(rcvd) < 68:               #68 is len of handshake message
                incomin = self.sock.recv(1024) 
                rcvd += incomin
                if incomin == b'':
                    raise socket.error('Connection just opened and Closed {}'.format(self.peerid))


            self.buffer += rcvd[68:]

            rcvd = rcvd[0:68]

            # Check if Handshake received is correct
            hsk = self.Make('Handshake')
            if not rcvd[0:20] == hsk[0:20] and rcvd[28:48] == hsk[28:48]:
                raise AssertionError

            return True

        except (socket.error, AssertionError) as e:
            self.buffer = b''

            try:
                self.sock.close()
            except socket.error:
                pass
            finally:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(30)
            return None



