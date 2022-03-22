# btc
btc is an implementation of a subset of the BitTorrent protocol to allow us to download torrents. It is mainly written for learning purposes.

## Usage
`python main.py <path to torrent file>`

## Implementation Overview
`bencode.py` contains code for parsing torrent files
`tracker.py` implements the tracker protocol
`peers.py` implements the peer protocol
`oracle.py` coordinates among the different threads we create (for downloading different pieces)

## ToDo
The downloads proceed real slow. For example, downloading a one GB file took us five and a half hours. Fix This.
Currently we support UDP trackers only. Add support for HTTP trackers.

