from logging import getLogger, StreamHandler, FileHandler, Formatter, DEBUG
from os import makedirs

from consts import ROOT_PATH


makedirs(ROOT_PATH + '/data', mode=0o777, exist_ok=True)

LOG_FILE = ROOT_PATH + '/data/app.log'
FILE_LEVEL = DEBUG


# console logger (root)
console = getLogger('fog_client_console')

# config console logger
_stream_handler = StreamHandler()
_stream_handler.setFormatter(
    Formatter(' *** %(levelname)s in %(module)s - %(message)s'))
console.addHandler(_stream_handler)
console.propagate = False


# file logger
file = getLogger('fog_client_file')

# config file logger
_file_handler = FileHandler(LOG_FILE)
_file_handler.setLevel(FILE_LEVEL)
_file_handler.setFormatter(
    Formatter('%(asctime)s - %(levelname)s in %(module)s - %(message)s'))
file.setLevel(FILE_LEVEL)
file.addHandler(_file_handler)
file.propagate = False
