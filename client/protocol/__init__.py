'''
    This module allows to import the correct protocol among multiple from 
    a single access point based on the mode (BROADCAST or ORCHESTRATOR).

    The protocol's responder is automatically started upon import.

    Methods:
    --------
    send_request(cos_id, data): Send a request to host a network application 
    of Class of Service (CoS) identified by cos_id, with data as input.
'''


from sys import path
from os.path import dirname


path.append(dirname(__file__))


# !!IMPORTANT!!
# This package relies on configuration received from the server after 
# connecting to it, so it must only be imported AFTER connect() is called


from os import getenv

from consts import SEND_TO_BROADCAST, SEND_TO_ORCHESTRATOR, SEND_TO_NONE


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


if PROTO_SEND_TO == SEND_TO_BROADCAST:
    from protocol_bcst import send_request, cos_names
elif PROTO_SEND_TO == SEND_TO_ORCHESTRATOR:
    from protocol_orch import send_request, cos_names
