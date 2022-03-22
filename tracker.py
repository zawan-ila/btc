from bencode import Bencode
import pprint
import socket
import secrets
import re
import hashlib
import queue
import requests


def IntToBytes(i, len = 4, endian = 'big', signed = False):
    return (i).to_bytes(len, endian, signed = signed)

def BytesToInt(byts, endian = 'big', signed = False):
    return int.from_bytes(byts, endian, signed = signed)

class Tracker:
    def __init__(self, torr_info):
        self.torr_info = torr_info
        self.torr_urls = [ torr_info['announce'] ]
        
        if torr_info['announce-list']:
            for url in torr_info['announce-list']:
                self.torr_urls += url
        
        # Keep only udp trackers

        self.torr_urls = list(filter(lambda f: f.startswith('udp'),self.torr_urls))
        self.url_idx = 0
        self.tot_urls = len(self.torr_urls)



        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.NumPieces = len(self.torr_info['info']['pieces']) // 20

        self.PieceLen = self.torr_info['info']['piece length']
        self.TorrLen = self.GetTorrLen()
        self.reconnect_time = 10*60
        self.filename = self.torr_info['info']['name']
        self.info_hash = self.GetInfoHash()


        if len(self.torr_urls) == 0:
            raise ValueError('No UDP Trackers available')

        self.multifileinfo = self.GetFilesInfo()
            
    
    def MakeConnectRequest(self):
        msg = b'\x00\x00\x04\x17\x27\x10\x19\x80' #connection id
        msg += b'\x00\x00\x00\x00' # connect identifier
        self.transcation_id = secrets.token_bytes(4) # transaction id
        msg += self.transcation_id 
        return msg
    
    def ParseConnectResponse(self, rsp):
        t_id = BytesToInt(rsp[4:8])
        self.conn_id = BytesToInt(rsp[8:16])
        # ignore the connect identifier?

    def MakeAnnounceRequest(self, pt, dwnld = 0, lft = 0, upld = 0):
        rqst = b""
        rqst += IntToBytes(self.conn_id, 8) # conn_id
        rqst += b"\x00\x00\x00\x01" #announce identifier
        self.new_t_id = secrets.token_bytes(4)
        rqst += self.new_t_id
        rqst += self.info_hash
        self.peer_id = secrets.token_bytes(20)
        rqst += self.peer_id
        rqst += IntToBytes(dwnld, 8)
        rqst += IntToBytes(lft, 8)
        rqst += IntToBytes(upld,8)
        rqst += IntToBytes(0,12) # event + ip + key
        rqst += IntToBytes(-1, signed = True) # num_want
        rqst += IntToBytes(pt, 2)  # harcoded port?
        return rqst


    def ParseAnnounceResponse(self,rsp):
        announce_identifier = BytesToInt(rsp[0:4])
        t_id = BytesToInt(rsp[4:8])
        self.reconnect_time = BytesToInt(rsp[8:12])
        self.leechers = BytesToInt(rsp[12:16])
        self.seeders = BytesToInt(rsp[16:20])
        self.PopulatePeerList(rsp[20:])

    def PopulatePeerList(self, addrs):
        while len(addrs) >= 6:
            new_peer_addr = addrs[:6]
            self.peerlist.append(self.GetIpPort(new_peer_addr))
            addrs = addrs[6:]

    
    def GetIpPort(self, peeraddr):
        ip = ''
        for i in range(4):
            ip += str(peeraddr[i])
            if not i==3:
                ip += '.'
        prt = int.from_bytes(peeraddr[4:], 'big', signed=False)
        return (ip,prt)


    def GetPeers(self, dwnld = 0, left = 0, upld = 0):
        self.peerlist = []
        
        for i in range(3):
            self.sock.settimeout(5*2**i)
            for i in range(self.tot_urls):
                '''
                Keep trying trackers unless we get a list of peers
                '''
                url = self.torr_urls[self.url_idx]

                try:
                    self.GetTrackerResponse(url, dwnld, left, upld)
                    self.url_idx = (self.url_idx + 1) % self.tot_urls  # For dynamism this is outside except
                    return self.peerlist
                
                except (socket.error, requests.exceptions.RequestException) as err:
                    print('Tracker Sent {}'.format(err))
                
                except Exception as e:
                    print('Tracker raised unexpected exception', e)
                
                self.url_idx = (self.url_idx + 1) % self.tot_urls # For dynamism this is outside except

        return None

    def GetTrackerResponse(self, url, dwnld, left, upld):

        match_obj = re.search("(?P<protocol>[a-zA-Z]+)://(?P<domain>[^:]+):(?P<port>\d+)", url)
        domain = match_obj.group('domain')
        port = int(match_obj.group('port'))
        addr = (domain, port)

        # Connect
        self.sock.sendto(self.MakeConnectRequest(), addr)
        data, adr = self.sock.recvfrom(2048)

        self.ParseConnectResponse(data)

        # Announce

        for i in range(9):
            try:
                pt = 6881+i
                self.sock.sendto(self.MakeAnnounceRequest(pt, dwnld, left, upld), addr)
                data, adr = self.sock.recvfrom(2048)
                break
            except OSError as os:
                print('Port Unavailable? ', os)

        self.ParseAnnounceResponse(data)


                    

    def GetHashes(self):
        MixedHashes = self.torr_info['info']['pieces']
        h = [MixedHashes[i:i+20] for i in range(0, 20*self.NumPieces, 20)]
        return h


    def GetInfoHash(self):

        to_hash = Bencode(self.torr_info['info']).encode()
        o = hashlib.sha1(to_hash).digest()
        return o

    def GetTorrLen(self):
        dic = self.torr_info['info']
        if 'length' in dic:
            #Single-file-torrent
            return dic['length']

        else:
            l = 0
            dic = dic['files']
            for i in dic:
                l += i['length']

            return l

    def GetFilesInfo(self):

        if 'length' in self.torr_info['info']:
            return None

        files = []
        lens = []

        for j in self.torr_info['info']['files']:
            files.append(j['path'][-1])
            lens.append(j['length'])

        return list(zip(files,lens))