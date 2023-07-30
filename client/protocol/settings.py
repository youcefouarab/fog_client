# !!IMPORTANT!!
# This module relies on config that is only present AFTER the connect()
# method is called, so only import after


from os import getenv
from logging import basicConfig, INFO

from model import CoS, Request
from consts import SEND_TO_BROADCAST, SEND_TO_ORCHESTRATOR, SEND_TO_NONE


# protocol config
_stp_enabled = getenv('NETWORK_STP_ENABLED', '').upper()
if _stp_enabled not in ('TRUE', 'FALSE'):
    print(' *** WARNING in protocol.__init__: '
          'NETWORK:STP_ENABLED parameter invalid or missing from received '
          'configuration. '
          'Defaulting to False.')
    _stp_enabled = 'FALSE'
STP_ENABLED = _stp_enabled == 'TRUE'

_proto_send_to = getenv('PROTOCOL_SEND_TO', None)
if (_proto_send_to not in (SEND_TO_BROADCAST,
                           SEND_TO_ORCHESTRATOR,
                           SEND_TO_NONE)
    or (_proto_send_to == SEND_TO_BROADCAST
        and not STP_ENABLED)):
    print(' *** WARNING in protocol.__init__: '
          'PROTOCOL:SEND_TO parameter invalid or missing from received '
          'configuration. '
          'Defaulting to ' + SEND_TO_NONE + ' (protocol will not be used).')
    _proto_send_to = SEND_TO_NONE
PROTO_SEND_TO = _proto_send_to

try:
    PROTO_TIMEOUT = float(getenv('PROTOCOL_TIMEOUT', None))
except:
    print(' *** WARNING in protocol: '
          'PROTOCOL:TIMEOUT parameter invalid or missing from received '
          'configuration. '
          'Defaulting to 1s.')
    PROTO_TIMEOUT = 1

try:
    PROTO_RETRIES = float(getenv('PROTOCOL_RETRIES', None))
except:
    print(' *** WARNING in protocol: '
          'PROTOCOL:RETRIES parameter invalid or missing from received '
          'configuration. '
          'Defaulting to 3 retries.')
    PROTO_RETRIES = 3

_proto_verbose = getenv('PROTOCOL_VERBOSE', '').upper()
if _proto_verbose not in ('TRUE', 'FALSE'):
    _proto_verbose = 'FALSE'
PROTO_VERBOSE = _proto_verbose == 'TRUE'

if PROTO_VERBOSE:
    basicConfig(level=INFO, format='%(message)s')

cos_dict = {cos.id: cos for cos in CoS.select()}
cos_names = {id: cos.name for id, cos in cos_dict.items()}

# dict of requests sent by consumer (keys are request IDs)
requests = {'_': None}  # '_' is placeholder
# fill with existing request IDs from DB to avoid conflict when generating IDs
requests.update(
    {req[0]: None for req in Request.select(fields=('id',), as_obj=False)})
