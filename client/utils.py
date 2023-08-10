from threading import Lock
from socket import socket, AF_INET, SOCK_DGRAM
from psutil import net_if_addrs
from ipaddress import ip_address, ip_network
from sys import exit as sys_exit


class SingletonMeta(type):
    '''
        Thread-safe implementation of Singleton design pattern.
    '''

    _instances = {}
    # to synchronize threads during first access to Singleton
    _lock: Lock = Lock()

    # possible changes to value of `__init__` argument do not affect returned
    # instance.
    def __call__(cls, *args, **kwargs):
        # Now, imagine that the program has just been launched. Since there's
        # no Singleton instance yet, multiple threads can simultaneously pass
        # the previous conditional and reach this point almost at the same
        # time. The first of them will acquire lock and will proceed further,
        # while the rest will wait here.
        with cls._lock:
            # The first thread to acquire the lock, reaches this conditional,
            # goes inside and creates the Singleton instance. Once it leaves
            # the lock block, a thread that might have been waiting for lock
            # release may enter this section. But since the Singleton field is
            # already initialized, the thread won't create a new object.
            if cls not in cls._instances:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
        return cls._instances[cls]


def get_iface(network: str):
    '''
        Returns interface name from given network address.
    '''

    try:
        net = ip_network(network)
    except:
        net = []
    for name, iface in net_if_addrs().items():
        for addr in iface:
            if addr.family == AF_INET and ip_address(addr.address) in net:
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
        return str(IP)


def get_ip(network: str = None, interface: str = None):
    '''
        Returns: 
            if network given: the IP of the node belonging to network;
            if interface given: the IP of the node attributed to interface; 
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
