from os import getenv
from threading import Thread
from time import sleep
from psutil import net_if_stats, net_io_counters
from psutil import cpu_count, cpu_percent, virtual_memory, disk_usage

from python_ovs_vsctl import (VSCtl, list_cmd_parser, VSCtlCmdExecError,
                              VSCtlCmdParseError)
from logger import console, file
from consts import ROOT_PATH
from utils import SingletonMeta


IS_SWITCH = getenv('IS_SWITCH', False)
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
        bandwidth, Tx and Rx packets on each network interface).

        If node is regular (physical, VM, etc.), the resources are gotten using
        the 'psutil' library. If it is a container (if the environment variable 
        IS_CONTAINER is set), then the resources are gotten using the Docker 
        control group (/sys/fs/cgroup).

        Attributes:
        -----------
        monitor_period: Time to wait before each measure. Default is 1s.

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
        \t\t    'tx_packets': <int>,\n
        \t\t    'rx_packets': <int>,\n
        \t  },\n
        }.

        Methods:
        --------
        start(): Start monitoring thread.

        stop(): Stop monitoring thread.
    '''

    def __init__(self, monitor_period: float = 1):
        self.measures = {}
        self.monitor_period = monitor_period

        self._run = False
        self._cpu_period = 0.1

    def start(self):
        '''
            Start monitoring thread.
        '''
        if not self._run:
            self._run = True
            Thread(target=self._start, daemon=True).start()

    def stop(self):
        '''
            Stop monitoring thread.
        '''
        self._run = False

    def set_monitor_period(self, period: float = 1):
        self.monitor_period = period

    def _start(self):
        _ovs_ports = []
        if IS_SWITCH:
            try:
                # get ports from OVS
                vsctl = VSCtl()
                stats = net_if_stats()
                for record in vsctl.run('list interface',
                                        parser=list_cmd_parser):
                    port = record.__dict__
                    name = port.get('name', None)
                    if name:
                        _ovs_ports.append(name)
                        # get associated "physical" interface
                        iface = port.get(
                            'status', {}).get('tunnel_egress_iface', None)
                        if iface:
                            # get missing stats
                            self.measures.setdefault(name, {})
                            self.measures[name]['capacity'] = float(
                                stats[iface].speed)
                            # other stats are already collected by server
            except (VSCtlCmdExecError, VSCtlCmdParseError) as e:
                console.error('Couldn\'t get OVS ports due to %s',
                              e.__class__.__name__)
                file.exception('Couldn\'t get OVS ports due to %s',
                               e.__class__.__name__)
        if IS_CONTAINER:
            # get usage of each CPU (in nanoseconds)
            try:
                percpu = open(
                    CGROUP_PATH + '/cpu/cpuacct.usage_percpu').read().split(' ')
                cpus = len(percpu) - 1  # don't count '\n'
            except Exception as e:
                cpus = cpu_count()
                console.error('Unable to read Docker control group for CPU '
                              '(%s). Switching to psutil',
                              e.__class__.__name__)
                file.exception('Unable to read Docker control group for CPU')
            self.measures['cpu_count'] = int(cpus)
            try:
                memory_total = float(open(
                    CGROUP_PATH + '/memory/memory.limit_in_bytes').read())
            except Exception as e:
                memory_total = virtual_memory().total
                console.error('Unable to read Docker control group for memory '
                              '(%s). Switching to psutil',
                              e.__class__.__name__)
                file.exception(
                    'Unable to read Docker control group for memory')
            self.measures['memory_total'] = float(memory_total / MEBI)
        else:
            cpus = cpu_count()
            self.measures['cpu_count'] = int(cpus)
            self.measures['memory_total'] = float(virtual_memory().total/MEBI)
        self.measures['disk_total'] = float(disk_usage(ROOT_PATH).total / GIBI)
        # get network I/O stats on each interface
        # by setting pernic to True
        io = net_io_counters(pernic=True)
        while self._run:
            # node specs
            if IS_CONTAINER:
                try:
                    self.measures['memory_free'] = float(memory_total - float(open(
                        CGROUP_PATH + '/memory/memory.usage_in_bytes').read())) / MEBI
                except:
                    file.exception('')
                    self.measures['memory_free'] = float(
                        virtual_memory().available / MEBI)
            else:
                self.measures['cpu_free'] = float(cpus - sum(
                    cpu_percent(interval=self._cpu_period, percpu=True)) / 100)
                self.measures['memory_free'] = float(
                    virtual_memory().available / MEBI)
            self.measures['disk_free'] = float(disk_usage(ROOT_PATH).free/GIBI)
            sleep(self._cpu_period)
            if IS_CONTAINER:
                # get CPU usage again after sleep
                try:
                    percpu_2 = open(
                        CGROUP_PATH + '/cpu/cpuacct.usage_percpu').read().split(' ')
                    cpu_usage = 0
                    for i, cpu in enumerate(percpu):
                        if cpu != '\n':
                            cpu_usage += ((float(percpu_2[i]) - float(cpu)) /
                                          (self._cpu_period / NANO))
                    self.measures['cpu_free'] = float(cpus - cpu_usage)
                    # update CPU usage for next iteration
                    percpu = percpu_2
                except:
                    file.exception('')
                    self.measures['cpu_free'] = float(cpus - sum(
                        cpu_percent(interval=self._cpu_period, percpu=True)) / 100)
            sleep(self.monitor_period - self._cpu_period)
            # get network I/O stats on each interface again after period
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
                    up_speed = up_bytes * BYTE / self.monitor_period
                    down_bytes = next.bytes_recv - prev.bytes_recv
                    down_speed = down_bytes * BYTE / self.monitor_period
                    #  get max speed (capacity)
                    max_speed = stats[iface].speed * MEGA
                    # calculate free bandwidth
                    bandwidth_up = (max_speed - up_speed) / MEGA
                    bandwidth_down = (max_speed - down_speed) / MEGA
                    #  save bandwidth measurement
                    self.measures.setdefault(iface, {})
                    self.measures[iface]['capacity'] = float(max_speed / MEGA)
                    self.measures[iface]['bandwidth_up'] = float(bandwidth_up)
                    self.measures[iface]['bandwidth_down'] = float(
                        bandwidth_down)
                    self.measures[iface]['tx_packets'] = int(next.packets_sent)
                    self.measures[iface]['rx_packets'] = int(next.packets_recv)
            # update network I/O stats for next iteration
            io = io_2


# for testing
if __name__ == '__main__':
    from pprint import pprint
    monitor = Monitor()
    monitor.start()
    while True:
        sleep(monitor.monitor_period)
        pprint(monitor.measures)
