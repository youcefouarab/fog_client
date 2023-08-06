# !!IMPORTANT!!
# This module relies on config that is only present AFTER the connect()
# method is called, so only import after


from os import getenv
from logging import basicConfig, INFO
from string import ascii_letters, digits
from random import choice

from model import CoS, Request, Attempt, Response
from api import add_request
from network import MY_IP
from consts import *


# protocol config
PROTO_NAME = 'MyProtocol'

_stp_enabled = getenv('NETWORK_STP_ENABLED', '').upper()
if _stp_enabled not in ('TRUE', 'FALSE'):
    print(' *** WARNING in protocol.settings: '
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
    print(' *** WARNING in protocol.settings: '
          'PROTOCOL:SEND_TO parameter invalid or missing from received '
          'configuration. '
          'Defaulting to ' + SEND_TO_NONE + ' (protocol will not be used).')
    _proto_send_to = SEND_TO_NONE
PROTO_SEND_TO = _proto_send_to

try:
    PROTO_TIMEOUT = float(getenv('PROTOCOL_TIMEOUT', None))
except:
    print(' *** WARNING in protocol.settings: '
          'PROTOCOL:TIMEOUT parameter invalid or missing from received '
          'configuration. '
          'Defaulting to 1s.')
    PROTO_TIMEOUT = 1

try:
    PROTO_RETRIES = float(getenv('PROTOCOL_RETRIES', None))
except:
    print(' *** WARNING in protocol.settings: '
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

# dict of requests sent as consumer (keys are request IDs)
requests = {'_': None}  # '_' is placeholder
# fill with existing request IDs from DB to avoid conflict when generating IDs
requests.update(
    {req[0]: None for req in Request.select(fields=('id',), as_obj=False)})

# dict of requests received as provider (keys are (src IP, request ID))
requests_ = {}

proto_states = {
    HREQ: 'host request (HREQ)',
    HRES: 'host response (HRES)',
    RREQ: 'resource reservation request (RREQ)',
    RRES: 'resource reservation response (RRES)',
    RACK: 'resource reservation acknowledgement (RACK)',
    RCAN: 'resource reservation cancellation (RCAN)',
    DREQ: 'data exchange request (DREQ)',
    DRES: 'data exchange response (DRES)',
    DACK: 'data exchange acknowledgement (DACK)',
    DCAN: 'data exchange cancellation (DCAN)',
    DWAIT: 'data exchange wait (DWAIT)',
}


class Request_(Request):
    def __init__(self, id):
        super().__init__(id, None, None)
        self._thread = None
        self._freed = True


def gen_req_id():
    id = '_'
    while id in requests:
        id = ''.join(
            choice(ascii_letters + digits) for _ in range(REQ_ID_LEN))
    return id


def save_req(req: Request):
    req.insert()
    for attempt in req.attempts.values():
        attempt.insert()
        for response in attempt.responses.values():
            response.insert()

    # save locally
    # if simulation is active (like mininet), create different CSV files for
    # different hosts (add IP address to file name)
    _suffix = '.' + MY_IP
    Request.as_csv(_suffix=_suffix)
    Attempt.as_csv(_suffix=_suffix)
    Response.as_csv(_suffix=_suffix)

    #  send request to server (for logging)
    sent, code = add_request(req)
    if not sent:
        print(' *** ERROR in protocol.settings: '
              'Request info failed to send to server for logging (%s). '
              'Only saved locally.' % str(code))
