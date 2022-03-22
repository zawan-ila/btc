
from tracker import *
from bencode import *
import sys
from oracle import *
import pprint

with open(sys.argv[1], "rb") as file: 
    s = file.read()

obj = Bencode(s)
torr_info = (obj.decode())


# pprint.pprint(torr_info)


o = Oracle(torr_info)


o.start()


