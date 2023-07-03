'''
    Simulator for getting, checking, reserving and freeing resources for 
    network applications, as well as their execution based on the requirements 
    of their Classes of Service (CoS).
    
    It can also function as a proxy of monitor, applying a filter to real 
    measurements (of CPU, RAM, disk, and bandwidth) to get simulated ones 
    based on capacities declared in conf.yml.

    Methods:
    --------
    get_resources(quiet, _all): Returns tuple of CPU count, free RAM, free 
    disk, free egress bandwidth and free ingress bandwidth.

    check_resources(request): Returns True if the current resources can satisfy 
    the requirements of request, False if not.
    
    reserve_resources(request): Subtract a quantity of resources to be reserved 
    for request from simulation variables.
    
    free_resources(request): Add back a quantity of resources reserved for 
    request to simulation variables.

    execute(data): Simulate the execution of network application by doing 
    sleeping for a determined period of time (by default randomly generated 
    between 0s and 1s).
'''


from os import getenv
from threading import Lock
from random import uniform
from time import sleep
from psutil import net_if_addrs
from logging import info

from model import Request
from common import MY_IP, MONITOR
import config


# host capacities (offered resources)
_host = 'DEFAULT'
if getenv('HOSTS_USE_DEFAULT', False) == 'True':
    _caps = getenv('HOSTS_DEFAULT', None)
else:
    _caps = getenv('HOSTS_' + MY_IP, None)
    if _caps == None:
        print(' *** WARNING in simulator: '
              'HOSTS:' + MY_IP + ' capacities missing from conf.yml '
              '(even though USE_DEFAULT is False). '
              'Defaulting to HOSTS:DEFAULT.')
        _caps = getenv('HOSTS_DEFAULT', None)
    else:
        _host = MY_IP
if _caps == None:
    print(' *** ERROR in simulator: '
          'HOSTS:DEFAULT capacities missing from conf.yml.')
    exit()
_caps = eval(_caps)

try:
    CPU = int(_caps['CPU'])
except:
    print(' *** ERROR in simulator: '
          'HOSTS:' + _host + ':CPU parameter invalid or missing from conf.yml.')
    exit()

try:
    RAM = int(_caps['RAM'])
except:
    print(' *** ERROR in simulator: '
          'HOSTS:' + _host + ':RAM parameter invalid or missing from conf.yml.')
    exit()

try:
    DISK = int(_caps['DISK'])
except:
    print(' *** ERROR in simulator: '
          'HOSTS:' + _host + ':DISK parameter invalid or missing from conf.yml.')
    exit()

try:
    EGRESS = int(_caps['EGRESS'])
except:
    print(' *** ERROR in simulator: '
          'HOSTS:' + _host + ':EGRESS parameter invalid or missing from conf.yml.')
    exit()

try:
    INGRESS = int(_caps['INGRESS'])
except:
    print(' *** ERROR in simulator: '
          'HOSTS:' + _host + ':INGRESS parameter invalid or missing from conf.yml.')
    exit()

# real monitoring config
SIM_ON = getenv('SIMULATOR_ACTIVE', False) == 'True'
my_iface = ''

if not SIM_ON:
    measures = MONITOR.measures
    wait = MONITOR.monitor_period

    while 'cpu_count' not in measures:
        sleep(wait)
    if CPU > measures['cpu_count']:
        print(' *** ERROR in simulator: '
              'Host cannot offer %d CPUs when it only has %d.' %
              (CPU, measures['cpu_count']))
        MONITOR.stop()
        exit()

    while 'memory_total' not in measures:
        sleep(wait)
    if RAM > measures['memory_total']:
        print(' *** ERROR in simulator: '
              'Host cannot offer %.2fMB of RAM when it only has %.2fMB.' %
              (RAM, measures['memory_total']))
        MONITOR.stop()
        exit()

    while 'disk_total' not in measures:
        sleep(wait)
    if DISK > measures['disk_total']:
        print(' *** ERROR in simulator: '
              'Host cannot offer %.2fGB of disk when it only has %.2fGB.' %
              (DISK, measures['disk_total']))
        MONITOR.stop()
        exit()

    for iface in net_if_addrs():
        if iface != 'lo':
            if not my_iface:
                my_iface = iface
            while 'bandwidth_up' not in measures.get(iface, {}):
                sleep(wait)
            if EGRESS > measures[iface]['bandwidth_up']:
                print(' *** ERROR in simulator: '
                      'Interface %s cannot offer %.2fMbps of egress bandwidth '
                      'when it only has %.2fMbps.' %
                      (iface, EGRESS, measures[iface]['bandwidth_up']))
                MONITOR.stop()
                exit()

            while 'bandwidth_down' not in measures.get(iface, {}):
                sleep(wait)
            if INGRESS > measures[iface]['bandwidth_down']:
                print(' *** ERROR in simulator: '
                      'Interface %s cannot offer %.2fMbps of ingress bandwidth '
                      'when it only has %.2fMbps.' %
                      (iface, INGRESS, measures[iface]['bandwidth_down']))
                MONITOR.stop()
                exit()

# simulation variables of reserved resources
_reserved = {
    'cpu': 0,
    'ram': 0,  # in MB
    'disk': 0,  # in GB
    'egress': 0,  # in Mbps  # TODO separate interfaces
    'ingress': 0,  # in Mbps  # TODO separate interfaces
}
_reserved_lock = Lock()  # for thread safety

# simulated exec time interval
try:
    SIM_EXEC_MIN = float(getenv('SIMULATOR_EXEC_MIN', None))
    try:
        SIM_EXEC_MAX = float(getenv('SIMULATOR_EXEC_MAX', None))
        if SIM_EXEC_MAX < SIM_EXEC_MIN:
            print(' *** WARNING in simulator: '
                  'SIMULATOR:EXEC_MIN and SIMULATOR:EXEC_MAX invalid. '
                  'Defaulting to [0s, 1s].')
            SIM_EXEC_MIN = 0
            SIM_EXEC_MAX = 1
    except:
        print(' *** WARNING in simulator: '
              'SIMULATOR:EXEC_MAX parameter invalid or missing from received '
              'configuration. '
              'Defaulting to [0s, 1s].')
        SIM_EXEC_MIN = 0
        SIM_EXEC_MAX = 1
except:
    print(' *** WARNING in simulator: '
          'SIMULATOR:EXEC_MIN parameter invalid or missing from received '
          'configuration. '
          'Defaulting to [0s, 1s].')
    SIM_EXEC_MIN = 0
    SIM_EXEC_MAX = 1


def get_resources(quiet: bool = False, _all: bool = False):
    '''
        Returns tuple of CPU count, free RAM, free disk, free egress bandwidth 
        and free ingress bandwidth.
    '''
    
    cpu = CPU - _reserved['cpu']
    _ram = RAM
    if not SIM_ON and measures['memory_free'] < RAM:
        _ram = measures['memory_free']
    ram = _ram - _reserved['ram']
    _disk = DISK
    if not SIM_ON and measures['disk_free'] < DISK:
        _disk = measures['disk_free']
    disk = _disk - _reserved['disk']
    _egress = EGRESS
    if not SIM_ON and measures[my_iface]['bandwidth_up'] < EGRESS:
        _egress = measures[my_iface]['bandwidth_up']
    egress = _egress - _reserved['egress']
    _ingress = INGRESS
    if not SIM_ON and measures[my_iface]['bandwidth_down'] < INGRESS:
        _ingress = measures[my_iface]['bandwidth_down']
    ingress = _ingress - _reserved['ingress']
    if _all:
        print('Host\'s real capacities')
        if not SIM_ON:
            print('    CPU        = %d\n'
                  '    TOTAL RAM  = %.2f MB\n'
                  '    FREE RAM   = %.2f MB\n'
                  '    TOTAL DISK = %.2f GB\n'
                  '    FREE DISK  = %.2f GB\n' % (measures['cpu_count'],
                                                  measures['memory_total'],
                                                  measures['memory_free'],
                                                  measures['disk_total'],
                                                  measures['disk_free']))
        else:
            print('Simulation is active, so real monitoring is unavailable')
        print('\nAvailable for reservation\n'
              '    CPU  = %d\n'
              '    RAM  = %.2f MB\n'
              '    DISK = %.2f GB\n' % (cpu, ram, disk))
    elif not quiet:
        info('current(cpu=%d, ram=%.2fMB, disk=%.2fGB, egress=%.2f, '
             'ingress=%.2f)' % (cpu, ram, disk, egress, ingress))
    return cpu, ram, disk, egress, ingress


def check_resources(req: Request, quiet: bool = False):
    '''
        Returns True if current resources can satisfy requirements of Request, 
        False if not.
    '''

    with _reserved_lock:
        min_cpu = req.get_min_cpu()
        min_ram = req.get_min_ram()
        min_disk = req.get_min_disk()
        if not quiet:
            info('required(cpu=%d, ram=%.2fMB, disk=%.2fGB)' %
                 (min_cpu, min_ram, min_disk))
        cpu, ram, disk, _, _ = get_resources(quiet)
        return cpu >= min_cpu and ram >= min_ram and disk >= min_disk


def reserve_resources(req: Request):
    '''
        Add quantity of resources to be reserved for Request to simulation 
        variables.

        Returns True if reserved, False if not.
    '''

    with _reserved_lock:
        min_cpu = req.get_min_cpu()
        min_ram = req.get_min_ram()
        min_disk = req.get_min_disk()
        info('required(cpu=%d, ram=%.2fMB, disk=%.2fGB)' % (
            min_cpu, min_ram, min_disk))
        cpu, ram, disk, _, _ = get_resources(quiet=True)
        if cpu >= min_cpu and ram >= min_ram and disk >= min_disk:
            _reserved['cpu'] += min_cpu
            _reserved['ram'] += min_ram
            _reserved['disk'] += min_disk
            get_resources()
            return True
        else:
            return False


def free_resources(req: Request):
    '''
        Subtract quantity of resources reserved for Request from simulation 
        variables.

        Returns True if freed, False if not.
    '''

    with _reserved_lock:
        _reserved['cpu'] -= req.get_min_cpu()
        if _reserved['cpu'] < 0:
            _reserved['cpu'] = 0
        _reserved['ram'] -= req.get_min_ram()
        if _reserved['ram'] < 0:
            _reserved['ram'] = 0
        _reserved['disk'] -= req.get_min_disk()
        if _reserved['disk'] < 0:
            _reserved['disk'] = 0
        get_resources()
        return True


def execute(data: bytes):
    '''
        Simulate execution of network application by doing nothing for a 
        determined period of time (by default randomly generated between 0s 
        and 1s).

        Returns result.
    '''

    sleep(uniform(SIM_EXEC_MIN, SIM_EXEC_MAX))
    return b'result'
