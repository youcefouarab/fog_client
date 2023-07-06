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
from common import MONITOR, IS_RESOURCE


SIM_ON = getenv('SIMULATOR_ACTIVE', False) == 'True'

if SIM_ON:
    try:
        CPU = int(getenv('HOST_CPU'))
    except:
        if not IS_RESOURCE:
            CPU = 0
        else:
            print(' *** ERROR in simulator: CPU argument invalid or missing.')
            exit()

    try:
        RAM = int(getenv('HOST_RAM'))
    except:
        if not IS_RESOURCE:
            RAM = 0
        else:
            print(' *** ERROR in simulator: RAM argument invalid or missing.')
            exit()

    try:
        DISK = int(getenv('HOST_DISK'))
    except:
        if not IS_RESOURCE:
            DISK = 0
        else:
            print(' *** ERROR in simulator: disk argument invalid or missing.')
            exit()

    try:
        EGRESS = int(getenv('HOST_EGRESS'))
    except:
        if not IS_RESOURCE:
            EGRESS = 0
        else:
            print(' *** ERROR in simulator: egress argument invalid or missing.')
            exit()

    try:
        INGRESS = int(getenv('HOST_INGRESS'))
    except:
        if not IS_RESOURCE:
            INGRESS = 0
        else:
            print(' *** ERROR in simulator: ingress argument invalid or missing.')
            exit()

else:
    # real monitoring config
    MEASURES = MONITOR.measures
    wait = MONITOR.monitor_period

    while ('cpu_count' not in MEASURES
           and 'memory_total' not in MEASURES
           and 'disk_total' not in MEASURES):
        sleep(wait)

    my_iface = ''
    for iface in net_if_addrs():
        if iface != 'lo':
            if not my_iface:
                my_iface = iface
            while ('bandwidth_up' not in MEASURES.get(iface, {})
                   and 'bandwidth_down' not in MEASURES.get(iface, {})):
                sleep(wait)

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
    
    cpu = ram = disk = egress = ingress = 0
    if SIM_ON:
        cpu = CPU - _reserved['cpu']
        ram = RAM - _reserved['ram']
        disk = DISK - _reserved['disk']
        egress = EGRESS - _reserved['egress']
        ingress = INGRESS - _reserved['ingress']
    elif IS_RESOURCE:
        cpu = MEASURES['cpu_count'] - _reserved['cpu']
        ram = MEASURES['memory_free'] - _reserved['ram']
        disk = MEASURES['disk_free'] - _reserved['disk']
        egress = MEASURES[my_iface]['bandwidth_up'] - _reserved['egress']
        ingress = MEASURES[my_iface]['bandwidth_down'] - _reserved['ingress']
    if _all:
        print('Host\'s real capacities')
        if not SIM_ON:
            print('    CPU        = %d\n'
                  '    TOTAL RAM  = %.2f MB\n'
                  '    FREE RAM   = %.2f MB\n'
                  '    TOTAL DISK = %.2f GB\n'
                  '    FREE DISK  = %.2f GB\n' % (MEASURES['cpu_count'],
                                                  MEASURES['memory_total'],
                                                  MEASURES['memory_free'],
                                                  MEASURES['disk_total'],
                                                  MEASURES['disk_free']))
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
