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
# This module relies on config that is only present AFTER the connect() 
# method is called, so only import after


from settings import PROTO_SEND_TO
from consts import SEND_TO_BROADCAST, SEND_TO_ORCHESTRATOR


if PROTO_SEND_TO == SEND_TO_BROADCAST:
    from protocol_bcst import send_request
elif PROTO_SEND_TO == SEND_TO_ORCHESTRATOR:
    from protocol_orch import send_request
