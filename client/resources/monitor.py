# !!IMPORTANT!!
# This module relies on config that is only present AFTER the connect()
# method is called, so only import after


from os import getenv, makedirs
from threading import Thread
from time import sleep
from psutil import (net_if_stats, net_io_counters, cpu_count, cpu_percent,
                    virtual_memory, disk_usage)

from python_ovs_vsctl import (VSCtl, list_cmd_parser, VSCtlCmdExecError,
                              VSCtlCmdParseError)

from my_iperf3 import iperf3_measures, iperf3_enabled
from wifi import (launch_hostapd, hostapd_dict, launch_iw, iw_dict,
                  wifi_capacity_map)
from logger import console, file
from consts import ROOT_PATH
from common import IS_SWITCH
from utils import SingletonMeta


IS_CONTAINER = getenv('IS_CONTAINER', False)
CGROUP_PATH = '/sys/fs/cgroup'

CAPS_PATH = ROOT_PATH + '/caps'

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
        self._ovs_port_to_iface = {}

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
        if IS_SWITCH:
            launch_hostapd()
        else:
            launch_iw()
        self._const_net()
        # get network I/O stats on each interface
        # by setting pernic to True
        io = net_io_counters(pernic=True)
        percpu = self._const_host()
        while self._run:
            percpu2 = self._var_host(percpu)
            # update network I/O stats for next iteration
            percpu = percpu2
            sleep(self.monitor_period - self._cpu_period)
            io2 = self._var_net(io)
            # update network I/O stats for next iteration
            io = io2

    def _const_host(self):
        # get host specs that are constant
        # (CPU count, RAM total, disk total)

        percpu = None
        psutil_mem_total = virtual_memory().total
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
                if memory_total > psutil_mem_total:
                    memory_total = psutil_mem_total
            except Exception as e:
                memory_total = psutil_mem_total
                console.error('Unable to read Docker control group for memory '
                              '(%s). Switching to psutil',
                              e.__class__.__name__)
                file.exception(
                    'Unable to read Docker control group for memory')
            self.measures['memory_total'] = float(memory_total / MEBI)
        else:
            cpus = cpu_count()
            self.measures['cpu_count'] = int(cpus)
            self.measures['memory_total'] = float(psutil_mem_total / MEBI)
        self.measures['disk_total'] = float(disk_usage(ROOT_PATH).total / GIBI)
        return percpu

    def _var_host(self, percpu):
        # get host specs that are variable
        # (CPU free, RAM free, disk free)

        percpu_2 = None
        if IS_CONTAINER:
            sleep(self._cpu_period)
            # get CPU usage again after sleep
            try:
                percpu_2 = open(
                    CGROUP_PATH + '/cpu/cpuacct.usage_percpu').read().split(' ')
                cpu_usage = 0
                for i, cpu in enumerate(percpu):
                    if cpu != '\n':
                        cpu_usage += ((float(percpu_2[i]) - float(cpu)) /
                                      (self._cpu_period / NANO))
                self.measures['cpu_free'] = max(
                    0.0, float(self.measures['cpu_count'] - cpu_usage))
            except:
                file.exception('')
                self.measures['cpu_free'] = max(
                    0.0, float(self.measures['cpu_count'] - sum(
                        cpu_percent(interval=self._cpu_period, percpu=True)) / 100))
            try:
                self.measures['memory_free'] = float(
                    self.measures['memory_total'] - float(open(
                        CGROUP_PATH + '/memory/memory.usage_in_bytes').read()) / MEBI)
            except:
                file.exception('')
                self.measures['memory_free'] = float(
                    virtual_memory().available / MEBI)
        else:
            self.measures['cpu_free'] = max(
                0.0, float(self.measures['cpu_count'] - sum(
                    cpu_percent(interval=self._cpu_period, percpu=True)) / 100))
            self.measures['memory_free'] = float(
                virtual_memory().available / MEBI)
        self.measures['disk_free'] = float(disk_usage(ROOT_PATH).free / GIBI)
        return percpu_2

    def _const_net(self):
        # get network specs that are constant
        # (capacity)

        stats = net_if_stats()

        def _get_capacity(ports):
            for port in ports:
                iface = port
                if IS_SWITCH:
                    iface = ports[port]
                if port != 'lo' and iface != 'lo' and iface not in iw_dict:
                    cap = None
                    update_file = True
                    if iperf3_enabled and iface not in hostapd_dict:
                        if port in iperf3_measures:
                            cap = iperf3_measures[port].get('sent_bps', None)
                            if cap != None:
                                cap = cap / MEGA
                    if cap == None:
                        if iperf3_enabled and iface not in hostapd_dict:
                            console.warning('Couldn\'t read capacity for %s '
                                            'from iPerf3. Switching to file' %
                                            port)
                        try:
                            cap = float(open(CAPS_PATH + '/' + port).read())
                        except Exception as e:
                            alt = 'psutil'
                            if iface in hostapd_dict:
                                alt = 'hostapd'
                            console.warning('Couldn\'t read capacity for %s '
                                            'from file caps/%s due to %s. '
                                            'Switching to %s' %
                                            (port, port, e.__class__.__name__,
                                             alt))
                            file.warning('Couldn\'t read capacity for %s from '
                                         'file caps/%s due to %s' %
                                         (port, port, e.__class__.__name__),
                                         exc_info=True)
                            if iface in hostapd_dict:
                                mode = hostapd_dict[iface].get('hw_mode', None)
                                cap = wifi_capacity_map.get(mode, None)
                                if cap == None:
                                    console.warning(
                                        'Couldn\'t read capacity for %s from '
                                        'wifi capacity map (mode \'%s\'). '
                                        'Switching to psutil' % (port, mode))
                            if cap == None:
                                cap = stats[iface].speed
                        else:
                            update_file = False
                    cap = float(cap)
                    self.measures.setdefault(port, {})
                    self.measures[port]['capacity'] = cap
                    if update_file:
                        console.info('Updating capacity in file caps/%s' %
                                     port)
                        makedirs(CAPS_PATH, mode=0o777, exist_ok=True)
                        f = open(CAPS_PATH + '/' + port, 'w')
                        f.write(str(cap))
                        f.close()

        if not IS_SWITCH:
            _get_capacity(stats)
        else:
            try:
                # get ports from OVS
                vsctl = VSCtl()
                records = vsctl.run('list interface',
                                    parser=list_cmd_parser)
                for record in records:
                    port = record.__dict__
                    name = port.get('name', None)
                    if name:
                        # get associated "physical" interface
                        iface = port.get(
                            'status', {}).get('tunnel_egress_iface', None)
                        if iface:
                            self._ovs_port_to_iface[name] = iface
                        elif name in stats:
                            self._ovs_port_to_iface[name] = name
            except (VSCtlCmdExecError, VSCtlCmdParseError) as e:
                console.error('Couldn\'t get OVS ports due to %s',
                              e.__class__.__name__)
                file.exception('Couldn\'t get OVS ports due to %s',
                               e.__class__.__name__)
            _get_capacity(self._ovs_port_to_iface)

    def _var_net(self, io):
        # get network specs that are variable
        # (bandwidth free, Tx packets, Rx packets)

        # get network I/O stats on each interface again after period
        io_2 = net_io_counters(pernic=True)
        ports = io
        if IS_SWITCH:
            ports = self._ovs_port_to_iface
        for port in ports:
            iface = port
            if IS_SWITCH:
                iface = self._ovs_port_to_iface[port]
            if port != 'lo' and iface != 'lo' and iface in io_2:
                # bandwidth
                # speed = (new bytes - old bytes) / period
                prev = io[iface]
                next = io_2[iface]
                bytes_sent = next.bytes_sent
                bytes_recv = next.bytes_recv
                up_bytes = bytes_sent - prev.bytes_sent
                up_speed = up_bytes * BYTE / self.monitor_period
                down_bytes = bytes_recv - prev.bytes_recv
                down_speed = down_bytes * BYTE / self.monitor_period
                #  get max speed (capacity)
                max_speed = 0
                if iface in iw_dict:
                    launch_iw()
                    max_speed = iw_dict[iface].get('tx bitrate', None)
                    try:
                        max_speed = float(max_speed.strip(' MBit/s'))
                    except:
                        max_speed = 0
                    self.measures.setdefault(port, {})
                    self.measures[port]['capacity'] = max_speed
                if port in self.measures:
                    max_speed = self.measures[port]['capacity'] * MEGA
                # calculate free bandwidth
                bandwidth_up = max(0, (max_speed - up_speed) / MEGA)
                bandwidth_down = max(0, (max_speed - down_speed) / MEGA)
                #  save bandwidth measurement
                self.measures.setdefault(port, {})
                self.measures[port]['bandwidth_up'] = float(bandwidth_up)
                self.measures[port]['bandwidth_down'] = float(bandwidth_down)
                self.measures[port]['tx_packets'] = int(next.packets_sent)
                self.measures[port]['rx_packets'] = int(next.packets_recv)
                self.measures[port]['tx_bytes'] = int(bytes_sent)
                self.measures[port]['rx_bytes'] = int(bytes_recv)
        return io_2


# for testing
if __name__ == '__main__':
    from pprint import pprint
    monitor = Monitor()
    monitor.start()
    while True:
        sleep(monitor.monitor_period)
        pprint(monitor.measures)
