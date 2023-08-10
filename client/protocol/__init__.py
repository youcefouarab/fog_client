'''
    This module allows to import the correct protocol among multiple from 
    a single access point based on the mode indicated by the server's 
    PROTOCOL:SEND_TO config parameter (BROADCAST or ORCHESTRATOR).

    The protocol's responder is automatically started upon import.

    Classes:
    --------
    MyProtocol: Class deriving from Scapy's Packet class to define the 
    communication protocol between hosts/orchestrator, including the packet 
    header's fields, as well as ways to detect if a packet is an answer to 
    another.

    MyProtocolAM: Class deriving from Scapy's AnsweringMachine class to define 
    the protocol's responder, which takes decisions and builds and sends 
    replies to received packets based on the protocol's state.

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


from .settings import PROTO_SEND_TO
from consts import SEND_TO_BROADCAST, SEND_TO_ORCHESTRATOR


if PROTO_SEND_TO == SEND_TO_BROADCAST:
    from .protocol_bcst import send_request, MyProtocol, MyProtocolAM
elif PROTO_SEND_TO == SEND_TO_ORCHESTRATOR:
    from .protocol_orch import send_request, MyProtocol, MyProtocolAM


if PROTO_SEND_TO in (SEND_TO_BROADCAST, SEND_TO_ORCHESTRATOR):
    # start the answering machine
    AM = MyProtocolAM(verbose=0)
    AM(bg=True)
