from logging import getLogger, basicConfig, DEBUG, FileHandler, Formatter

from consts import ROOT_PATH


LOG_FILE = ROOT_PATH + '/data/app.log'
FILE_LEVEL = DEBUG


# console logger (root)
console = getLogger()

# config console logger
basicConfig(format=' *** %(levelname)s in %(module)s - %(message)s')

# file logger
file = getLogger(__name__)

# config file logger
_handler = FileHandler(LOG_FILE)
_handler.setLevel(FILE_LEVEL)
_handler.setFormatter(
    Formatter('%(asctime)s - %(levelname)s in %(module)s - %(message)s'))
file.setLevel(FILE_LEVEL)
file.addHandler(_handler)
file.propagate = False
