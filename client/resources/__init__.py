'''
    This module allows to import the correct methods and parameters for 
    resources check-up or manipulation from a single access point, whether 
    they are real or simulated (based on the server's SIMULATOR:ACTIVE config 
    parameter).

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


from sys import path
from os.path import dirname


path.append(dirname(__file__))


# !!IMPORTANT!!
# This module relies on config that is only present AFTER the connect() 
# method is called, so only import after


from .monitor import IS_CONTAINER
from .network import NETWORK_ADDRESS, BROADCAST_IP, MY_IFACE, MY_IP
from .simulator import (check_resources, get_resources, reserve_resources,
                        free_resources, execute, MONITOR, MONITOR_PERIOD,
                        MEASURES, IS_RESOURCE, SIM_ON, CPU, RAM, DISK, LIMIT,
                        THRESHOLD, CPU_THRESHOLD, RAM_THRESHOLD,
                        DISK_THRESHOLD, SIM_EXEC_MIN, SIM_EXEC_MAX)
