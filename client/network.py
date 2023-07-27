# !!IMPORTANT!!
# This module relies on configuration received from the server after
# connecting to it, so it must only be imported AFTER connect() is called


from os import getenv
from ipaddress import IPv4Network

from utils import get_iface, get_ip


NETWORK_ADDRESS = getenv('NETWORK_ADDRESS', None)

if not NETWORK_ADDRESS:
    #print(' *** WARNING in protocol: '
    #      'NETWORK:ADDRESS parameter missing from received configuration. '
    #      'Defaulting to broadcast IP 255.255.255.255.')
    BROADCAST_IP = '255.255.255.255'
else:
    try:
        BROADCAST_IP = IPv4Network(
            NETWORK_ADDRESS).broadcast_address.exploded
    except:
        #print(' *** WARNING in protocol: '
        #      'NETWORK:ADDRESS parameter invalid in received configuration. '
        #      'Defaulting to broadcast IP 255.255.255.255.')
        BROADCAST_IP = '255.255.255.255'

IFACE = get_iface(NETWORK_ADDRESS)
MY_IP = get_ip(interface=IFACE)
