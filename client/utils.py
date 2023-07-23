from socket import socket, AF_INET, SOCK_DGRAM
from psutil import net_if_addrs
from ipaddress import ip_address, ip_network


def get_ip():
    '''
        Returns the "primary" IP of the node (the one with a default route).
    '''

    with socket(AF_INET, SOCK_DGRAM) as s:
        s.settimeout(0)
        try:
            # doesn't even have to be reachable
            s.connect(('10.254.254.254', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP


def get_iface_from_network(network: str):
    '''
        Returns interface name from given network address.
    '''

    for name, iface in net_if_addrs().items():
        for addr in iface:
            if (addr.family == AF_INET 
                    and ip_address(addr.address) in ip_network(network)):
                return name


def get_iface_from_bcst(bcst: str):
    '''
        Returns interface name from given broadcast address.
    '''

    for name, iface in net_if_addrs().items():
        for addr in iface:
            if addr.family == AF_INET and addr.broadcast == bcst:
                return name
