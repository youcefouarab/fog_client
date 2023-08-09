'''
    Simulator for getting, checking, reserving and freeing resources for 
    network applications, as well as their execution based on the requirements 
    of their Classes of Service (CoS).
    
    It can also function as a proxy of monitor, applying a filter to real 
    measurements (of CPU, RAM, disk) to get simulated ones based on capacities 
    declared in conf.yml.

    Methods:
    --------
    get_resources(quiet): Returns tuple of free CPU, free RAM, and free disk.

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


# !!IMPORTANT!!
# This module relies on config that is only present AFTER the connect()
# method is called, so only import after


from os import getenv
from threading import Lock
from random import uniform
from time import sleep
from psutil import net_if_addrs

from model import Request
from common import IS_RESOURCE
from network import MY_IFACE
from monitor import Monitor
from logger import console, file
from utils import all_exit


# monitoring config
MONITOR = Monitor()

try:
    MONITOR_PERIOD = float(getenv('MONITOR_PERIOD', None))
except:
    console.warn('MONITOR_PERIOD parameter invalid or missing from received '
                 'configuration. '
                 'Defaulting to 1s')
    file.warn('MONITOR_PERIOD parameter invalid or missing from received '
              'configuration', exc_info=True)
    MONITOR_PERIOD = 1

MONITOR.set_monitor_period(MONITOR_PERIOD)
MONITOR.start()

_sim_on = getenv('SIMULATOR_ACTIVE', '').upper()
if _sim_on not in ('TRUE', 'FALSE'):
    console.warn('SIMULATOR:ACTIVE parameter invalid or missing from received '
                 'configuration. '
                 'Defaulting to False')
    file.warn('SIMULATOR:ACTIVE parameter (%s) invalid or missing from '
              'received configuration', _sim_on)
    _sim_on = 'FALSE'
SIM_ON = _sim_on == 'TRUE'

if SIM_ON:
    try:
        CPU = int(getenv('HOST_CPU'))
    except:
        if not IS_RESOURCE:
            CPU = 0
        else:
            console.error('CPU argument invalid or missing')
            file.exception('CPU argument invalid or missing')
            all_exit()

    try:
        RAM = int(getenv('HOST_RAM'))
    except:
        if not IS_RESOURCE:
            RAM = 0
        else:
            console.error('RAM argument invalid or missing')
            file.exception('RAM argument invalid or missing')
            all_exit()

    try:
        DISK = int(getenv('HOST_DISK'))
    except:
        if not IS_RESOURCE:
            DISK = 0
        else:
            console.error('Disk argument invalid or missing')
            file.exception('Disk argument invalid or missing')
            all_exit()

    '''
    try:
        EGRESS = int(getenv('HOST_EGRESS'))
    except:
        if not IS_RESOURCE:
            EGRESS = 0
        else:
            console.error('Egress argument invalid or missing')
            file.exception('Egress argument invalid or missing')
            all_exit()

    try:
        INGRESS = int(getenv('HOST_INGRESS'))
    except:
        if not IS_RESOURCE:
            INGRESS = 0
        else:
            console.error('Ingress argument invalid or missing')
            file.exception('Ingress argument invalid or missing')
            all_exit()
    '''

else:
    # wait for monitor
    MEASURES = MONITOR.measures
    wait = 0.1
    while ('cpu_count' not in MEASURES
           or 'cpu_free' not in MEASURES
           or 'memory_total' not in MEASURES
           or 'memory_free' not in MEASURES
           or 'disk_total' not in MEASURES
           or 'disk_free' not in MEASURES):
        sleep(wait)

    # for iface in net_if_addrs():
    #    if iface != 'lo':
    #        while ('capacity' not in MEASURES.get(iface, {})
    #               or 'bandwidth_up' not in MEASURES.get(iface, {})
    #               or 'bandwidth_down' not in MEASURES.get(iface, {})):
    #            sleep(wait)

# limits and thresholds
if IS_RESOURCE:
    try:
        _limit = float(getenv('RESOURCE_LIMIT', None))
        if _limit < 0 or _limit > 100:
            console.warn('Resource limit argument invalid (must be %). '
                         'Defaulting to 0%')
            file.warn('Resource limit argument (%s) invalid', str(_limit))
            _limit = 0
    except:
        console.warn('Resource limit argument invalid or missing. '
                     'Defaulting to 0%')
        file.warn('Resource limit argument invalid or missing', exc_info=True)
        _limit = 0
    # limit is the max resource usage (e.g. can't surpass 80%)
    LIMIT = _limit / 100
    # threshold is the complementary of limit
    # (i.e. the remaining 20% that we can't reserve)
    THRESHOLD = 1 - LIMIT
    # both are gross values (to get percentages, multiply by 100)

    if SIM_ON:
        CPU_THRESHOLD = CPU * THRESHOLD
        RAM_THRESHOLD = RAM * THRESHOLD
        DISK_THRESHOLD = DISK * THRESHOLD
    else:
        CPU_THRESHOLD = MEASURES['cpu_count'] * THRESHOLD
        RAM_THRESHOLD = MEASURES['memory_total'] * THRESHOLD
        DISK_THRESHOLD = MEASURES['disk_total'] * THRESHOLD

# simulation variables of reserved resources
_reserved = {
    'cpu': 0,
    'ram': 0,  # in MB
    'disk': 0,  # in GB
    # 'egress': 0,  # in Mbps  # TODO separate interfaces
    # 'ingress': 0,  # in Mbps  # TODO separate interfaces
}
_reserved_lock = Lock()  # for thread safety

# simulated exec time interval
try:
    SIM_EXEC_MIN = float(getenv('SIMULATOR_EXEC_MIN', None))
    try:
        SIM_EXEC_MAX = float(getenv('SIMULATOR_EXEC_MAX', None))
        if SIM_EXEC_MAX < SIM_EXEC_MIN:
            console.warn('SIMULATOR:EXEC_MIN and SIMULATOR:EXEC_MAX '
                         'parameters invalid in received configuration. '
                         'Defaulting to [0s, 1s]')
            file.warn('SIMULATOR:EXEC_MIN and SIMULATOR:EXEC_MAX '
                      'parameters (%s and %s) invalid in received '
                      'configuration', str(SIM_EXEC_MIN), str(SIM_EXEC_MAX))
            SIM_EXEC_MIN = 0
            SIM_EXEC_MAX = 1
    except:
        console.warn('SIMULATOR:EXEC_MAX parameter invalid or missing from '
                     'received configuration. '
                     'Defaulting to [0s, 1s]')
        file.warn('SIMULATOR:EXEC_MAX parameter invalid or missing from '
                  'received configuration', exc_info=True)
        SIM_EXEC_MIN = 0
        SIM_EXEC_MAX = 1
except:
    console.warn('SIMULATOR:EXEC_MIN parameter invalid or missing from '
                 'received configuration. '
                 'Defaulting to [0s, 1s]')
    file.warn('SIMULATOR:EXEC_MIN parameter invalid or missing from '
              'received configuration', exc_info=True)
    SIM_EXEC_MIN = 0
    SIM_EXEC_MAX = 1


def get_resources(quiet: bool = False, _all: bool = False):
    '''
        Returns tuple of free CPU, free RAM and free disk.
    '''

    cpu = ram = disk = 0
    if SIM_ON:
        cpu = CPU - _reserved['cpu']
        ram = RAM - _reserved['ram']
        disk = DISK - _reserved['disk']
        # egress = EGRESS - _reserved['egress']
        # ingress = INGRESS - _reserved['ingress']
    elif IS_RESOURCE:
        cpu = MEASURES['cpu_free'] - _reserved['cpu']
        ram = MEASURES['memory_free'] - _reserved['ram']
        disk = MEASURES['disk_free'] - _reserved['disk']
        # egress = MEASURES[MY_IFACE]['bandwidth_up'] - _reserved['egress']
        # ingress = MEASURES[MY_IFACE]['bandwidth_down'] - _reserved['ingress']
    if _all:
        print('\nHost\'s real capacities')
        if not SIM_ON:
            print('    CPU COUNT  = %d (%.2f%s)\n'
                  '    CPU FREE   = %.2f (%.2f%s)\n'
                  '    RAM TOTAL  = %.2f MB\n'
                  '    RAM FREE   = %.2f MB\n'
                  '    DISK TOTAL = %.2f GB\n'
                  '    DISK FREE  = %.2f GB' % (MEASURES['cpu_count'],
                                                MEASURES['cpu_count'] *
                                                100, '%',
                                                MEASURES['cpu_free'],
                                                MEASURES['cpu_free'] *
                                                100, '%',
                                                MEASURES['memory_total'],
                                                MEASURES['memory_free'],
                                                MEASURES['disk_total'],
                                                MEASURES['disk_free']))
        else:
            print('Simulation is active, so real monitoring is unavailable')
        if IS_RESOURCE:
            print('\nAvailable for reservation\n'
                  '    CPU  = %.2f (%.2f%s)\n'
                  '    RAM  = %.2f MB\n'
                  '    DISK = %.2f GB\n'
                  '(with an overall usage limit of %.2f%s)' % (cpu,
                                                               cpu * 100, '%',
                                                               ram, disk,
                                                               LIMIT * 100, '%'))
        else:
            print('No resources to offer in this mode')
        print()
    elif not quiet:
        console.info('current(cpu=%.2f, ram=%.2fMB, disk=%.2fGB)' %
                     (cpu, ram, disk))
    return cpu, ram, disk


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
            console.info('required(cpu=%d, ram=%.2fMB, disk=%.2fGB)' %
                         (min_cpu, min_ram, min_disk))
        cpu, ram, disk = get_resources(quiet)
        return (cpu - min_cpu >= CPU_THRESHOLD
                and ram - min_ram >= RAM_THRESHOLD
                and disk - min_disk >= DISK_THRESHOLD)


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
        console.info('required(cpu=%d, ram=%.2fMB, disk=%.2fGB)' %
                     (min_cpu, min_ram, min_disk))
        cpu, ram, disk = get_resources(quiet=True)
        if (cpu - min_cpu >= CPU_THRESHOLD
                and ram - min_ram >= RAM_THRESHOLD
                and disk - min_disk >= DISK_THRESHOLD):
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
