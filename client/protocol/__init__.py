from sys import path
from os.path import dirname


path.append(dirname(__file__))


from os import getenv

from consts import SEND_TO_BROADCAST, SEND_TO_ORCHESTRATOR, SEND_TO_NONE


STP_ENABLED = getenv('NETWORK_STP_ENABLED', False) == 'True'
_proto_send_to = getenv('PROTOCOL_SEND_TO', None)
if (_proto_send_to == None
        or (_proto_send_to != SEND_TO_BROADCAST
            and _proto_send_to != SEND_TO_ORCHESTRATOR
            and _proto_send_to != SEND_TO_NONE)
        or (_proto_send_to == SEND_TO_BROADCAST
            and not STP_ENABLED)):
    print(' *** WARNING in protocol.__init__: '
          'PROTOCOL:SEND_TO parameter invalid or missing from received '
          'configuration. '
          'Defaulting to ' + SEND_TO_NONE + ' (protocol will not be used).')
    _proto_send_to = SEND_TO_NONE
PROTO_SEND_TO = _proto_send_to


if PROTO_SEND_TO == SEND_TO_BROADCAST:
    from protocol_bcst import send_request, cos_names
elif PROTO_SEND_TO == SEND_TO_ORCHESTRATOR:
    from protocol_orch import send_request, cos_names
