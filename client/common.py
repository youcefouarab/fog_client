from os import getenv

from monitor import Monitor


MONITOR = Monitor()

# conf
SERVER_IP = getenv('SERVER_IP', None)
if SERVER_IP == None:
    print(' *** ERROR in common: server argument missing')
    exit()

IS_RESOURCE = getenv('IS_RESOURCE', False) == 'True'
