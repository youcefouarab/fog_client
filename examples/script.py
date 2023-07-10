from os import getenv, environ
from threading import Thread
from time import sleep

from context import *
from client.consts import MODE_CLIENT, MODE_RESOURCE
from client.client import connect


MODE = getenv('MODE', None)
if MODE not in (MODE_CLIENT, MODE_RESOURCE):
    print(' *** ERROR in script: '
          'MODE environment variable invalid or missing.')
    exit()

try:
    environ['SERVER_IP'], environ['SERVER_API_PORT'] = getenv('SERVER', None).split(':')
except:
    print(' *** ERROR in script: '
          'SERVER environment variable invalid or missing. '
          'Format must be IP:PORT (e.g. 127.0.0.1:8080).')
    exit()

ID = getenv('ID', None)
LABEL = getenv('LABEL', None)

_verb = getenv('VERBOSE', None)
if _verb == None or _verb.upper() not in ('TRUE', 'FALSE'):
    _verb = 'False'
VERBOSE = _verb.upper() == 'TRUE'

environ['PROTOCOL_VERBOSE'] = str(VERBOSE)

if MODE == MODE_RESOURCE:
    environ['IS_RESOURCE'] = 'True'
    environ['HOST_CPU'] = getenv('CPU', 'None')
    environ['HOST_RAM'] = getenv('RAM', 'None')
    environ['HOST_DISK'] = getenv('DISK', 'None')
    #environ['HOST_INGRESS'] = getenv('INGRESS', 'None')
    #environ['HOST_EGRESS'] = getenv('EGRESS', 'None')


print()
connect(MODE, verbose=VERBOSE, id=ID, label=LABEL)
print()
sleep(1)


try:
    COS_ID = int(getenv('COS_ID', None))
except:
    print(' *** WARNING in script: '
          'COS_ID environment variable invalid or missing. '
          'Defaulting to 1 (best-effort).')
    COS_ID = 1

try:
    DELAY = float(getenv('DELAY', None))
except:
    print(' *** WARNING in script: '
          'DELAY environment variable invalid or missing. '
          'Defaulting to 1s.')
    DELAY = 1

try:
    INTERVAL = float(getenv('INTERVAL', None))
except:
    print(' *** WARNING in script: '
          'INTERVAL environment variable invalid or missing. '
          'Defaulting to 1s.')
    INTERVAL = 1

try:
    THREADS = int(getenv('THREADS', None))
except:
    print(' *** WARNING in script: '
          'THREADS environment variable invalid or missing. '
          'Defaulting to 1.')
    THREADS = 1

try:
    LIMIT = int(getenv('LIMIT', None))
except:
    print(' *** WARNING in script: '
          'LIMIT environment variable invalid or missing. '
          'Defaulting to 1.')
    LIMIT = 1

_seq = getenv('SEQUENTIAL', None)
if _seq == None or _seq.upper() not in ('TRUE', 'FALSE'):
    print(' *** WARNING in script: '
          'SEQUENTIAL environment variable invalid or missing. '
          'Defaulting to False.')
    _seq = 'False'
SEQUENTIAL = _seq.upper() == 'TRUE'

_data = getenv('DATA', None)
if _data == None:
    print(' *** WARNING in script: '
          'DATA environment variable missing. '
          'No data will be sent.')
    _data = ''
DATA = _data.encode()


from client.protocol import send_request


def _send_request(index: int, cos_id: int, data: bytes):
    print('%d-' % index, send_request(cos_id=cos_id, data=data))


def _send_requests():
    limit = LIMIT
    index = 0
    sleep(DELAY)
    while limit != 0:
        limit -= 1
        index += 1
        if SEQUENTIAL:
            _send_request(index, COS_ID, DATA)
        else:
            Thread(target=_send_request, args=(
                index, COS_ID, DATA)).start()
        sleep(INTERVAL)


for thread in range(THREADS):
    Thread(target=_send_requests).start()
