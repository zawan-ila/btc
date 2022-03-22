import re
from pprint import pprint

class Bencode:
    def __init__(self, str):
        self.data = str
        self.idx = 0

    def decode(self):
        '''
        Treat the byte string self.data as bencoded
        and decode it
        '''


        if self.idx >= len(self.data):
            raise IndexError 

        if self.data[self.idx] in b'0123456789':
            '''
            String
            '''
            strlen = (re.search(b"^\d+", self.data[self.idx:])).group()
            self.idx += (len(strlen)+1) # 1 is for the :
            to_ret = self.data[self.idx: self.idx + int(strlen)]
            self.idx += int(strlen)

            try:
                to_ret = to_ret.decode()
            except UnicodeDecodeError:
                pass
            return to_ret


        elif self.data[self.idx] == (b'i')[0]:
            '''
            Int
            '''
            self.idx += 1
            strint = re.search(b"^-?\d+", self.data[self.idx:]).group()
            self.idx += len(strint)
            if self.data[self.idx] != (b'e')[0]:
                raise ValueError("Input Not Correct")
            self.idx += 1

            return int(strint)
            

            
        elif self.data[self.idx] == (b'l')[0]:
            '''
            List
            '''
            l = []
            self.idx += 1
            while self.data[self.idx] != (b'e')[0]:
                l.append(self.decode())
            self.idx += 1
            return l
                

            

        elif self.data[self.idx] == (b'd')[0]:
            '''
            Dictionary
            '''
            d = {}
            self.idx += 1
            while self.data[self.idx] != (b'e')[0]:
                getnextkey = self.decode()
                getnextval = self.decode()
                d[getnextkey] = getnextval

            self.idx += 1
            return d

        else:

            raise ValueError("This is not a valid bencoded string")

    
    def encode(self):
        
        if isinstance(self.data, int):
            return b"i" + str(self.data).encode() + b"e"
        
        elif isinstance(self.data, str):
            return (str(len(self.data)) + ':' + self.data).encode()
        
        elif isinstance(self.data, list):
            to_ret = b"l"
            for elem in self.data:
                to_ret += Bencode(elem).encode()
            to_ret += b"e"
        
        elif isinstance(self.data, dict):
            to_ret = b"d"
            for k,v in self.data.items():
                to_ret += Bencode(k).encode()
                to_ret += Bencode(v).encode()
            
            to_ret += b"e"

        elif isinstance(self.data, bytes):
            return str(len(self.data)).encode() + b':' + self.data
        
        else:
            print(self.data)
            raise ValueError('Cant B Encode Data')
        
        
        return to_ret





