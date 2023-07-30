from os import getenv
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

SERVER = getenv('SERVER', None)

ID = getenv('ID', None)
LABEL = getenv('LABEL', None)

_verbose = getenv('VERBOSE', '').upper()
if _verbose not in ('TRUE', 'FALSE'):
    _verbose = 'FALSE'
VERBOSE = _verbose == 'TRUE'

if MODE == MODE_RESOURCE:
    CPU = getenv('CPU', 'None')
    RAM = getenv('RAM', 'None')
    DISK = getenv('DISK', 'None')
    #INGRESS = getenv('INGRESS', 'None')
    #EGRESS = getenv('EGRESS', 'None')


print()
if MODE == MODE_CLIENT:
    connect(MODE, SERVER, verbose=VERBOSE, id=ID, label=LABEL)
if MODE == MODE_RESOURCE:
    connect(MODE, SERVER, verbose=VERBOSE, id=ID, label=LABEL, cpu=CPU, 
            ram=RAM, disk=DISK)
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

_sequential = getenv('SEQUENTIAL', '').upper()
if _sequential not in ('TRUE', 'FALSE'):
    print(' *** WARNING in script: '
          'SEQUENTIAL environment variable invalid or missing. '
          'Defaulting to False.')
    _sequential = 'FALSE'
SEQUENTIAL = _sequential == 'TRUE'

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
