'''
Mode can be client, resource or switch
'''
MODE = 'client'

'''
Node ID
'''
ID = '00:00:00:00:10:10'

'''
Node label
'''
LABEL = 'h1'

'''
Class of Service list

id  name              
1   best-effort       
2   cpu-bound         
3   streaming         
4   conversational    
5   interactive       
6   real-time         
7   mission-critical  
'''
COS_ID = 1

'''
Send a request every INTERVAL seconds
'''
INTERVAL = 0.1

'''
THREADS running in parallel
'''
THREADS = 1

'''
Stop when LIMIT requests (per thread) are sent (-1 is infinite)
'''
LIMIT = 100

'''
If SEQUENTIAL, wait for previous response before sending next request
'''
SEQUENTIAL = False

'''
DATA bytes to send
'''
DATA = b'data + program'


#####################################
#### !! DO NOT EDIT FROM HERE !! ####
#####################################


from os import getenv
from threading import Thread
from time import sleep

from context import *
from client.client import connect
from client.common import SEND_TO_BROADCAST, SEND_TO_ORCHESTRATOR, SEND_TO_NONE


connect(MODE, id=ID, label=LABEL)
sleep(1)


STP_ENABLED = getenv('NETWORK_STP_ENABLED', False) == 'True'
_proto_send_to = getenv('PROTOCOL_SEND_TO', None)
if (_proto_send_to == None
        or (_proto_send_to != SEND_TO_BROADCAST
            and _proto_send_to != SEND_TO_ORCHESTRATOR
            and _proto_send_to != SEND_TO_NONE)
        or (_proto_send_to == SEND_TO_BROADCAST
            and not STP_ENABLED)):
    print(' *** WARNING in script: '
          'PROTOCOL:SEND_TO parameter invalid or missing from received '
          'configuration. '
          'Defaulting to ' + SEND_TO_NONE + ' (protocol will not be used).')
    _proto_send_to = SEND_TO_NONE
PROTO_SEND_TO = _proto_send_to


if PROTO_SEND_TO == SEND_TO_BROADCAST:
    from client.protocol_bcst import send_request
    print('BCST')
elif PROTO_SEND_TO == SEND_TO_ORCHESTRATOR:
    from client.protocol_orch import send_request
    print('CTRL')
else:
    print(' *** ERROR in script:'
            'protocol cannot be used when PROTOCOL:SEND_TO is ' + SEND_TO_NONE)
    exit()


def _send_request(index: int, cos_id: int, data: bytes):
    print('%d-' % index, send_request(cos_id=cos_id, data=data))


def _send_requests():
    _limit = LIMIT
    index = 0
    while _limit != 0:
        _limit -= 1
        index += 1
        if SEQUENTIAL:
            _send_request(index, COS_ID, DATA)
        else:
            Thread(target=_send_request, args=(
                index, COS_ID, DATA)).start()
        sleep(INTERVAL)


for thread in range(THREADS):
    Thread(target=_send_requests).start()
