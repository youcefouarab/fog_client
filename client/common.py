# !!IMPORTANT!!
# This module relies on config that is only present AFTER the connect()
# method is called, so only import after


from os import getenv


SERVER_IP = getenv('SERVER_IP', None)
if SERVER_IP == None:
    print(' *** ERROR in common: server argument missing')
    exit()

_is_resource = getenv('IS_RESOURCE', '').upper()
if _is_resource not in ('TRUE', 'FALSE'):
    _is_resource = 'FALSE'
IS_RESOURCE = _is_resource == 'TRUE'
