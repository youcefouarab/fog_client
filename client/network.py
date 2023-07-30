# !!IMPORTANT!!
# This module relies on config that is only present AFTER the connect()
# method is called, so only import after


from os import getenv
from ipaddress import ip_address

from utils import get_iface, get_ip


NETWORK_ADDRESS = getenv('NETWORK_ADDRESS', None)

if not NETWORK_ADDRESS:
    # print(' *** WARNING in network: '
    #      'NETWORK:ADDRESS parameter missing from received configuration. '
    #      'Defaulting to broadcast IP 255.255.255.255.')
    BROADCAST_IP = '255.255.255.255'
else:
    try:
        BROADCAST_IP = ip_address(NETWORK_ADDRESS).broadcast_address.exploded
    except:
        # print(' *** WARNING in network: '
        #      'NETWORK:ADDRESS parameter invalid in received configuration. '
        #      'Defaulting to broadcast IP 255.255.255.255.')
        BROADCAST_IP = '255.255.255.255'

IFACE = get_iface(NETWORK_ADDRESS)
MY_IP = get_ip(interface=IFACE)
