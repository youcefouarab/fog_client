from os import getenv
from threading import Thread
from time import sleep
from logging import INFO, WARNING

from context import *
from client.consts import MODE_CLIENT, MODE_RESOURCE
from client.client import connect
from client.logger import console, file
from client.utils import all_exit


_verbose = getenv('VERBOSE', '').upper()
if _verbose not in ('TRUE', 'FALSE'):
    _verbose = 'FALSE'
VERBOSE = _verbose == 'TRUE'

console.setLevel(INFO if VERBOSE else WARNING)

MODE = getenv('MODE', None)
_MODES = (MODE_CLIENT, MODE_RESOURCE)
if MODE not in _MODES:
    console.error('MODE environment variable invalid or missing (must be '
                  '%s or %s)', _MODES)
    file.error('MODE environment variable (%s) invalid or missing (must be '
               '%s or %s)', MODE, _MODES)
    all_exit()

SERVER = getenv('SERVER', None)

ID = getenv('ID', None)
LABEL = getenv('LABEL', None)

if MODE == MODE_RESOURCE:
    LIMIT = getenv('LIMIT', 'None')
    CPU = getenv('CPU', 'None')
    RAM = getenv('RAM', 'None')
    DISK = getenv('DISK', 'None')
    # INGRESS = getenv('INGRESS', 'None')
    # EGRESS = getenv('EGRESS', 'None')


print()
if MODE == MODE_CLIENT:
    connect(MODE, SERVER, verbose=VERBOSE, id=ID, label=LABEL)
if MODE == MODE_RESOURCE:
    connect(MODE, SERVER, verbose=VERBOSE, id=ID, label=LABEL, limit=LIMIT,
            cpu=CPU, ram=RAM, disk=DISK)
print()
sleep(1)


try:
    COS_ID = int(getenv('COS_ID', None))
except:
    console.warning('COS_ID environment variable invalid or missing. '
                    'Defaulting to 1 (best-effort)')
    file.warning(
        'COS_ID environment variable invalid or missing', exc_info=True)
    COS_ID = 1

try:
    DELAY = float(getenv('DELAY', None))
except:
    console.warning('DELAY environment variable invalid or missing. '
                    'Defaulting to 1s')
    file.warning(
        'DELAY environment variable invalid or missing', exc_info=True)
    DELAY = 1

try:
    INTERVAL = float(getenv('INTERVAL', None))
except:
    console.warning('INTERVAL environment variable invalid or missing. '
                    'Defaulting to 1s')
    file.warning('INTERVAL environment variable invalid or missing',
                 exc_info=True)
    INTERVAL = 1

try:
    THREADS = int(getenv('THREADS', None))
except:
    console.warning('THREADS environment variable invalid or missing. '
                    'Defaulting to 1')
    file.warning(
        'THREADS environment variable invalid or missing', exc_info=True)
    THREADS = 1

try:
    TOTAL = int(getenv('TOTAL', None))
except:
    console.warning('TOTAL environment variable invalid or missing. '
                    'Defaulting to 1')
    file.warning(
        'TOTAL environment variable invalid or missing', exc_info=True)
    TOTAL = 1

_sequential = getenv('SEQUENTIAL', '').upper()
if _sequential not in ('TRUE', 'FALSE'):
    console.warning('SEQUENTIAL environment variable invalid or missing. '
                    'Defaulting to False')
    file.warning('SEQUENTIAL environment (%s) variable invalid or missing',
                 _sequential)
    _sequential = 'FALSE'
SEQUENTIAL = _sequential == 'TRUE'

_data = getenv('DATA', None)
if _data == None:
    console.warning('DATA environment variable missing. '
                    'No data will be sent')
    file.warning('DATA environment variable missing')
    _data = ''
DATA = _data.encode()


from client.protocol import send_request


def _send_request(index: int, cos_id: int, data: bytes):
    print('%d-' % index, send_request(cos_id=cos_id, data=data))


def _send_requests():
    total = TOTAL
    index = 0
    sleep(DELAY)
    while total != 0:
        total -= 1
        index += 1
        if SEQUENTIAL:
            _send_request(index, COS_ID, DATA)
        else:
            Thread(target=_send_request, args=(
                index, COS_ID, DATA)).start()
        sleep(INTERVAL)


for thread in range(THREADS):
    Thread(target=_send_requests).start()
