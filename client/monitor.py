from os import getenv
from threading import Thread
from time import monotonic, sleep
from psutil import net_if_stats, net_io_counters
from psutil import cpu_count, cpu_percent, virtual_memory, disk_usage
from socket import socket, AF_INET, SOCK_STREAM

from meta import SingletonMeta
from consts import ROOT_PATH
from utils import get_ip


IS_CONTAINER = getenv('IS_CONTAINER', False)
CGROUP_PATH = '/sys/fs/cgroup'

MEGA = 10e+6
MEBI = 1048576
GIGA = 10e+9
GIBI = 1073741824
BYTE = 8
NANO = 10e-9


class Monitor(metaclass=SingletonMeta):
    '''
        Singleton class for monitoring the state of resources of the node it's 
        running on (total and free CPUs, total and free memory size, total and 
        free disk size, as well as total capacity, free egress and ingress 
        bandwidth, Tx and Rx packets, and delay on each network interface).

        If node is regular (physical, VM, etc.), the resources are gotten using
        the 'psutil' library. If it is a container (if the environment variable 
        IS_CONTAINER is set), then the resources are gotten using the Docker 
        control group (/sys/fs/cgroup).

        Attributes:
        -----------
        monitor_period: Time to wait before each measure. Default is 1s.

        ping_host_ip: Destination IP address to which delay is calculated, 
        default is 8.8.8.8.

        ping_host_port: Destination port number to which delay is calculated, 
        default is 443.

        ping_timeout: Time to wait before declaring delay as infinite. Default 
        is 4s.

        measures: Dict containing the most recent measures in the following 
        structure: 

        {\n
        \t  'cpu_count': <int>,\n
        \t  'cpu_free': <float>,\n
        \t  'memory_total: <float>, # in MiB\n
        \t  'memory_free': <float>, # in MiB\n
        \t  'disk_total': <float>, # in GiB\n
        \t  'disk_free': <float>, # in GiB\n
        \t  'iface_name': {\n
        \t\t    'capacity': <float>, # in Mbit/s\n
        \t\t    'bandwidth_up': <float>, # in Mbit/s\n
        \t\t    'bandwidth_down': <float>, # in Mbit/s\n
        \t\t    'delay': <float>, # in s\n
        \t\t    'tx_packets': <int>,\n
        \t\t    'rx_packets': <int>,\n
        \t  },\n
        }.

        Methods:
        --------
        start(): Start monitoring thread.

        stop(): Stop monitoring thread.
    '''

    def __init__(self, monitor_period: float = 1,
                 ping_host_ip: str = '8.8.8.8', ping_host_port: int = 443,
                 ping_timeout: float = 4):
        self.measures = {}
        self.monitor_period = monitor_period
        self.ping_host_ip = ping_host_ip
        self.ping_host_port = ping_host_port
        self.ping_timeout = ping_timeout

        self._run = False

    def start(self):
        '''
            Start monitoring thread.
        '''
        if not self._run:
            self._run = True
            Thread(target=self._start).start()

    def stop(self):
        '''
            Stop monitoring thread.
        '''
        self._run = False

    def set_monitor_period(self, period: float = 1):
        self.monitor_period = period

    def set_ping_host(self, ip: str = '8.8.8.8', port: int = 443):
        self.ping_host_ip = ip
        self.ping_host_port = port

    def set_ping_timeout(self, timeout: float = 4):
        self.ping_timeout = timeout

    def _start(self):
        if IS_CONTAINER:
            # get usage of each CPU (in nanoseconds)
            percpu = open(
                CGROUP_PATH + '/cpu/cpuacct.usage_percpu').read().split(' ')
        # get network I/O stats on each interface
        # by setting pernic to True
        io = net_io_counters(pernic=True)
        while self._run:
            # node specs
            if IS_CONTAINER:
                cpus = len(percpu) - 1  # don't count '\n'
                self.measures['cpu_count'] = cpus
                memory_total = float(open(
                    CGROUP_PATH + '/memory/memory.limit_in_bytes').read())
                self.measures['memory_total'] = memory_total / MEBI  # in MiB
                memory_usage = float(open(
                    CGROUP_PATH + '/memory/memory.usage_in_bytes').read())
                self.measures['memory_free'] = (
                    memory_total - memory_usage) / MEBI  # in MiB
            else:
                cpus = cpu_count()
                self.measures['cpu_count'] = cpus
                self.measures['cpu_free'] = (cpus
                                             - sum(cpu_percent(percpu=True)) / 100)
                mem = virtual_memory()
                self.measures['memory_total'] = mem.total / MEBI  # in MiB
                self.measures['memory_free'] = mem.available / MEBI  # in MiB
            disk = disk_usage(ROOT_PATH)
            self.measures['disk_total'] = disk.total / GIBI  # in GiB
            self.measures['disk_free'] = disk.free / GIBI  # in GiB
            '''
            for iface in io:
                if iface != 'lo':
                    # delay
                    # use thread so it's asynchronous (in case of timeout)
                    Thread(target=self._get_delay, args=(iface,)).start()
            '''
            sleep(self.monitor_period)
            if IS_CONTAINER:
                # get CPU usage again
                percpu_2 = open(
                    CGROUP_PATH + '/cpu/cpuacct.usage_percpu').read().split(' ')
                cpu_usage = 0
                for i, cpu in enumerate(percpu):
                    if cpu != '\n':
                        cpu_usage += ((float(percpu_2[i]) - float(cpu))
                                      / (self.monitor_period / NANO))
                self.measures['cpu_free'] = cpus - cpu_usage
            # get network I/O stats on each interface again
            io_2 = net_io_counters(pernic=True)
            # get network interfaces stats
            stats = net_if_stats()
            for iface in io:
                if iface != 'lo' and iface in io_2 and iface in stats:
                    # bandwidth
                    # speed = (new bytes - old bytes) / period
                    # current speed = max(up speed, down speed)
                    prev = io[iface]
                    next = io_2[iface]
                    up_bytes = next.bytes_sent - prev.bytes_sent
                    up_speed = up_bytes * BYTE / self.monitor_period  # in bits/s
                    down_bytes = next.bytes_recv - prev.bytes_recv
                    down_speed = down_bytes * BYTE / self.monitor_period  # in bits/s
                    #  get max speed (capacity)
                    max_speed = stats[iface].speed * MEGA  # in bits/s
                    # calculate free bandwidth
                    bandwidth_up = (max_speed - up_speed) / MEGA  # in Mbits/s
                    bandwidth_down = (max_speed - down_speed) / \
                        MEGA  # in Mbits/s
                    #  save bandwidth measurement
                    self.measures.setdefault(iface, {})
                    # in Mbits/s
                    self.measures[iface]['capacity'] = max_speed / MEGA
                    self.measures[iface]['bandwidth_up'] = bandwidth_up
                    self.measures[iface]['bandwidth_down'] = bandwidth_down
                    self.measures[iface]['tx_packets'] = next.packets_sent
                    self.measures[iface]['rx_packets'] = next.packets_recv
                # if interface is removed during monitor period
                # remove from measures dict
                elif iface not in io_2 or iface not in stats:
                    self.measures.pop(iface, None)
            if IS_CONTAINER:
                # update CPU usage for next iteration
                percpu = percpu_2
            # update network I/O stats for next iteration
            io = io_2

    def _get_delay(self, via_iface: str):
        '''
            Connect to host:port via interface specified by name and calculate 
            total delay before response.

            If timeout set, connection will be closed after timeout seconds 
            and delay will be considered infinite.
        '''
        with socket(AF_INET, SOCK_STREAM) as s:
            # bind socket to interface if specified
            if via_iface:
                ip = get_ip(interface=via_iface)
                if ip:
                    s.bind((ip, 0))
            # set timeout in case of errors
            s.settimeout(self.ping_timeout)
            # start timer
            t_start = monotonic()
            # try to connect to host
            try:
                s.connect((self.ping_host_ip, self.ping_host_port))
                # stop timer and calculate delay
                delay = (monotonic() - t_start)
            except:
                # if exception, connection wasn't acheived correctly
                delay = float('inf')
            finally:
                # close connection
                s.close()
                self.measures.setdefault(via_iface, {})
                self.measures[via_iface]['delay'] = delay


# for testing
if __name__ == '__main__':
    from pprint import pprint
    monitor = Monitor()
    monitor.start()
    while True:
        sleep(monitor.monitor_period)
        pprint(monitor.measures)
