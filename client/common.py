# !!IMPORTANT!!
# This module relies on config that is only present AFTER the connect()
# method is called, so only import after


from os import getenv

from logger import console, file
from utils import all_exit


SERVER_IP = getenv('SERVER_IP', None)
if SERVER_IP == None:
    console.error('Server argument missing')
    file.error('Server argument missing')
    all_exit()

_is_switch = getenv('IS_SWITCH', '').upper()
if _is_switch not in ('TRUE', 'FALSE'):
    _is_switch = 'FALSE'
IS_SWITCH = _is_switch == 'TRUE'

_is_resource = getenv('IS_RESOURCE', '').upper()
if _is_resource not in ('TRUE', 'FALSE'):
    _is_resource = 'FALSE'
IS_RESOURCE = _is_resource == 'TRUE'

_limit = 0
_threshold = 1
if IS_RESOURCE:
    try:
        _limit = float(getenv('RESOURCE_LIMIT', None))
        if _limit < 0 or _limit > 100:
            console.warning('Resource limit argument invalid (must be %). '
                            'Defaulting to 0%')
            file.warning('Resource limit argument (%s) invalid', str(_limit))
            _limit = 0
    except:
        console.warning('Resource limit argument invalid or missing. '
                        'Defaulting to 0%')
        file.warning('Resource limit argument invalid or missing',
                     exc_info=True)
        _limit = 0
    # limit is the max resource usage (e.g. can't surpass 80%)
    _limit = _limit / 100
    # threshold is the complementary of limit
    # (i.e. the remaining 20% that we can't reserve)
    _threshold = 1 - _limit
    # both are gross values (to get percentages, multiply by 100)
LIMIT = _limit
THRESHOLD = _threshold
