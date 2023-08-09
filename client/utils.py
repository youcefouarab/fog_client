from socket import socket, AF_INET, SOCK_DGRAM
from psutil import net_if_addrs
from ipaddress import ip_address, ip_network
from sys import exit as sys_exit


def get_iface(network: str):
    '''
        Returns interface name from given network address.
    '''

    for name, iface in net_if_addrs().items():
        for addr in iface:
            if (addr.family == AF_INET
                    and ip_address(addr.address) in ip_network(network)):
                return name


def get_default_ip():
    '''
        Returns the "primary" IP of the node (the one with a default route).
    '''

    with socket(AF_INET, SOCK_DGRAM) as s:
        s.settimeout(0)
        try:
            # doesn't even have to be reachable
            s.connect(('255.255.255.254', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP


def get_ip(network: str = None, interface: str = None):
    '''
        Returns: 
            if network given: the IP of the node belonging to network
            if interface given: the IP of the node attributed to interface 
            if network/interface not given or incorrect: the IP of the node 
            with a default route.
    '''

    name = interface
    if network != None:
        name = get_iface(network)
    for addr in net_if_addrs().get(name, []):
        if addr.family == AF_INET:
            return addr.address
    return get_default_ip()


def all_exit():
    sys_exit()
