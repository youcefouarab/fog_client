'''
    Definition of the communication protocol between hosts in ORCHESTRATOR 
    (ORCH) mode, including the packets' header and the protocol's responder, 
    using the library Scapy.

    Classes:
    --------
    MyProtocol: Class deriving from Scapy's Packet class to define the 
    communication protocol between hosts in ORCHESTRATOR (ORCH) mode, including 
    the packet header's fields, as well as ways to detect if a packet is an 
    answer to another.

    MyProtocolAM: Class deriving from Scapy's AnsweringMachine class to define 
    the protocol's responder, which takes decisions and builds and sends 
    replies to received packets based on the protocol's state.

    Methods:
    --------
    send_request(cos_id, data): Send a request to host a network application 
    of Class of Service (CoS) identified by cos_id, with data as input.
'''


# !!IMPORTANT!!
# This module relies on configuration received from the server after
# connecting to it, so it must only be imported AFTER connect() is called


from os import getenv
from threading import Thread, Event
from time import time
from string import ascii_letters, digits
from random import choice
from logging import info, basicConfig, INFO

from scapy.all import (Packet, ByteEnumField, StrLenField, IntEnumField,
                       StrField, IntField, ConditionalField, AnsweringMachine,
                       bind_layers, send, sendp, srp1, sr1, Ether, IP)

from simulator import (check_resources, reserve_resources, free_resources,
                       execute)
from model import Request, Attempt, CoS
from network import IFACE, MY_IP
from consts import *


# decoy controller/orchestrator
ORCH_MAC = getenv('CONTROLLER_DECOY_MAC', None)
if ORCH_MAC == None:
    print(' *** ERROR in protocol: '
          'CONTROLLER:DECOY_MAC parameter missing from received configuration.')
    exit()

ORCH_IP = getenv('CONTROLLER_DECOY_IP', None)
if ORCH_IP == None:
    print(' *** ERROR in protocol: '
          'CONTROLLER:DECOY_IP parameter missing from received configuration.')
    exit()

# protocol config
try:
    PROTO_TIMEOUT = float(getenv('PROTOCOL_TIMEOUT', None))
except:
    print(' *** WARNING in protocol: '
          'PROTOCOL:TIMEOUT parameter invalid or missing from received '
          'configuration. '
          'Defaulting to 1s.')
    PROTO_TIMEOUT = 1

try:
    PROTO_RETRIES = float(getenv('PROTOCOL_RETRIES', None))
except:
    print(' *** WARNING in protocol: '
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

# dict of requests sent by consumer (keys are request IDs)
requests = {'_': None}  # '_' is placeholder
# fill with existing request IDs from DB to avoid conflict when generating IDs
requests.update(
    {req[0]: None for req in Request.select(fields=('id',), as_obj=False)})

# dict of requests received by provider (keys are (src IP, request ID))
_requests = {}

# dict of data exchange events (keys are (src IP, request ID))
_events = {}


class _Request(Request):
    def __init__(self, id):
        super().__init__(id, None, None)
        self._thread = None
        self._freed = True


class MyProtocol(Packet):
    '''
        Class deriving from Scapy's Packet class to define the communication 
        protocol between hosts in ORCHESTRATOR (ORCH) mode, including the 
        packet header's fields, as well as ways to detect if a packet is an 
        answer to another.

        Fields:
        -------
        state: 1 byte indicating the state of the protocol, enumeration of 
        HREQ (1) (host request), HRES (2) (host response), RREQ (3) (resource 
        reservation request), RRES (4) (resource reservation response), RACK 
        (5) (resource reservation acknowledgement), RCAN (6) (resource 
        reservation cancellation), DREQ (7) (data exchange request), DRES (8) 
        (data exchange response), DACK (9) (data exchange acknowledgement), 
        DCAN (10) (data exchange cancellation), DWAIT (11) (data exchange 
        wait). Default is HREQ (1).

        req_id: String of 10 bytes indicating the request's ID. Default is ''.

        attempt_no: Integer of 4 bytes indicating the attempt number. Default 
        is 1.

        cos_id: Integer of 4 bytes indicating the application's CoS ID. Default 
        is 1 (best-effort). Conditional field for state == HREQ (1) or state 
        == RREQ (3).

        data: String of undefined number of bytes containing input data and 
        possibly program to execute. Default is ''. Conditional field for 
        state == DREQ (7) or state == DRES (8).

        src_mac: String of 17 bytes indicating the source node's MAC address 
        (for intermediate communications between potential hosts and 
        orchestrator, where Ether layer no longer contains source node's MAC 
        address). Conditional field for state == RREQ (3), state == RRES (4), 
        state == DACK (9) or state == DCAN (10).

        src_ip: String of 15 bytes indicating the source node's IPv4 address 
        (for intermediate communications between potential hosts and 
        orchestrator, where IP layer no longer contains source node's IP 
        address). Conditional field for state == RREQ (3), state == RRES (4), 
        state == RACK (5), state == RCAN (6), state == DACK (9) or state == 
        DCAN (10).

        host_mac: String of 17 bytes indicating the selected host's MAC 
        address to be communicated to the source node. Conditional field for 
        state == HRES (2).

        host_ip: String of 15 bytes indicating the selected host's IPv4 
        address to be communicated to the source node. Conditional field for 
        state == HRES (2).
    '''

    _states = {
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

    name = 'MyProtocol'
    fields_desc = [
        ByteEnumField('state', HREQ, _states),
        StrLenField('req_id', '', lambda _: REQ_ID_LEN),
        IntField('attempt_no', 1),
        ConditionalField(IntEnumField('cos_id', 0, cos_names),
                         lambda pkt: pkt.state == HREQ or pkt.state == RREQ),
        ConditionalField(StrField('data', ''),
                         lambda pkt: pkt.state == DREQ or pkt.state == DRES),
        ConditionalField(StrLenField('src_mac', ' ' * MAC_LEN,
                                     lambda _: MAC_LEN),
                         lambda pkt: pkt.state == RREQ or pkt.state == RRES
                         or pkt.state == RACK or pkt.state == RCAN
                         or pkt.state == DACK or pkt.state == DCAN),
        ConditionalField(StrLenField('src_ip', ' ' * IP_LEN, lambda _: IP_LEN),
                         lambda pkt: pkt.state == RREQ or pkt.state == RRES
                         or pkt.state == RACK or pkt.state == RCAN
                         or pkt.state == DACK or pkt.state == DCAN),
        ConditionalField(StrLenField('host_mac', ' ' * MAC_LEN,
                                     lambda _: MAC_LEN),
                         lambda pkt: pkt.state == HRES or pkt.state == DCAN
                         or pkt.state == DACK),
        ConditionalField(StrLenField('host_ip', ' ' * IP_LEN,
                                     lambda _: IP_LEN),
                         lambda pkt: pkt.state == HRES or pkt.state == DCAN
                         or pkt.state == DACK),
    ]

    def show(self):
        if PROTO_VERBOSE:
            print()
            return super().show()

    def hashret(self):
        _suffix = b''
        # if (self.state == RREQ or self.state == RRES or self.state == DACK
        #        or self.state == DCAN):
        #    _suffix = self.src_ip
        return self.req_id + str(self.attempt_no).encode() + _suffix

    def answers(self, other):
        if (isinstance(other, MyProtocol)
            # host request expects host response
            and (other.state == HREQ and self.state == HRES
                 # resource reservation request expects resource reservation
                 # response or resource reservation cancellation
                 or other.state == RREQ and (self.state == RRES
                                             or self.state == RCAN)
                 # resource reservation response expects data exchange request
                 # or resource reservation cancellation
                 or other.state == RRES and (self.state == RACK
                                             or self.state == RCAN)
                 # data exchange request expects data exchange response, data
                 # exchange wait, or data exchange cancellation
                 or other.state == DREQ and (self.state == DRES
                                             or self.state == DWAIT
                                             or self.state == DCAN)
                 # data exchange response expects data exchange acknowledgement
                 # or data exchange cancellation
                 or other.state == DRES and (self.state == DACK
                                             or self.state == DCAN))):
            return 1
        return 0


# for scapy to be able to dissect MyProtocol packets
bind_layers(Ether, MyProtocol)
bind_layers(IP, MyProtocol)


class MyProtocolAM(AnsweringMachine):
    '''
        Class deriving from Scapy's AnsweringMachine class to define the 
        protocol's responder, which takes decisions and builds and sends 
        replies to received packets based on the protocol's state.
    '''

    function_name = 'mpam'
    sniff_options = {'filter': 'inbound', 'iface': IFACE}
    send_function = staticmethod(send)
    send_options = {'iface': IFACE}

    def is_request(self, req):
        # a packet must have Ether, IP and MyProtocol layers
        return (Ether in req and IP in req and MyProtocol in req
                # and no other layer
                and not any((layer is not Ether
                             and layer is not IP
                             and layer is not MyProtocol)
                            for layer in req.layers())
                # and not self
                and req[IP].src != MY_IP
                and req[IP].src != DEFAULT_IP
                # and must have an ID
                and req[MyProtocol].req_id != b'')

    def make_reply(self, req):
        my_proto = req[MyProtocol]
        ip_src = req[IP].src
        req_id = my_proto.req_id.decode()
        _req_id = (ip_src, req_id)
        state = my_proto.state

        # provider receives resource reservation request
        if state == RREQ and ip_src == ORCH_IP:
            _req_id = (my_proto.src_ip.decode().strip(), req_id)
            # if new request
            if _req_id not in _requests:
                _requests[_req_id] = _Request(req_id)
                _requests[_req_id].state = RREQ
                _requests[_req_id].cos = cos_dict[my_proto.cos_id]
            # host request must not have already been reserved
            if (_requests[_req_id].state == RREQ
                    or _requests[_req_id].state == RCAN):
                info('Recv resource reservation request from orchestrator')
                my_proto.show()
                info('Reserving resources')
                # if resources are actually reserved
                if reserve_resources(_requests[_req_id]):
                    _requests[_req_id].state = RRES
                    _requests[_req_id]._freed = False
                # else they became no longer sufficient in time between
                # HREQ and RREQ
                else:
                    info('Resources are not sufficient')
                    info('Send resource reservation cancellation to '
                         'orchestrator')
                    _requests[_req_id].state = RREQ
                    my_proto.state = RCAN
                    return (IP(dst=ORCH_IP) / my_proto)
            # if resources reserved
            if _requests[_req_id].state == RRES:
                Thread(target=self._respond_resources,
                       args=(my_proto, _req_id)).start()
            return

        # provider receives data exchange request
        if state == DREQ and _req_id in _requests:
            if _req_id in _events:
                _events[_req_id].set()
            # already executed
            if _requests[_req_id].state == DRES:
                my_proto.state = DRES
                my_proto.data = _requests[_req_id].result
                return IP(dst=ip_src) / my_proto
            # still executing
            if (_requests[_req_id].state == DREQ
                    and _requests[_req_id]._thread != None):
                my_proto.state = DWAIT
                return IP(dst=ip_src) / my_proto
            info('Recv data exchange request from %s' % ip_src)
            my_proto.show()
            # if request was cancelled before
            if _requests[_req_id].state == RCAN:
                info('This request arrived late')
                # if resources are still available
                if check_resources(_requests[_req_id], quiet=True):
                    info('but resources are still available')
                    info('Reserving resources')
                    reserve_resources(_requests[_req_id])
                    _requests[_req_id].state = RRES
                    _requests[_req_id]._freed = False
                else:
                    info('and resources are no longer sufficient')
                    info('Send data exchange cancellation to %s' % ip_src)
                    _requests[_req_id].state = DCAN
                    my_proto.state = DCAN
                    my_proto.src_mac = req[Ether].src
                    my_proto.src_ip = ip_src.ljust(IP_LEN, ' ')
                    my_proto.host_mac = req[Ether].dst
                    my_proto.host_ip = req[IP].dst.ljust(IP_LEN, ' ')
                    return IP(dst=ip_src) / my_proto
            # new execution
            if _requests[_req_id].state == RRES:
                _requests[_req_id].state = DREQ
                _requests[_req_id]._thread = Thread(
                    target=self._respond_data,
                    args=(my_proto, ip_src, _req_id))
                _requests[_req_id]._thread.start()
            return

        # consumer receives late data exchange response
        if state == DRES and req_id in requests:
            # if no other response was already accepted
            if not requests[req_id].dres_at:
                dres_at = time()
                requests[req_id].dres_at = dres_at
                requests[req_id].state = DRES
                requests[req_id].host = ip_src
                requests[req_id].result = my_proto.data
                requests[req_id].attempts[my_proto.attempt_no].state = DRES
                requests[req_id].attempts[my_proto.attempt_no].dres_at = dres_at
                info('Recv data exchange response from %s' % ip_src)
                my_proto.show()
                if req_id in _events:
                    _events[req_id].set()
                info('Send data exchange acknowledgement to orchestrator')
                my_proto.state = DACK
                my_proto.host_mac = req[Ether].src
                my_proto.host_ip = ip_src.ljust(IP_LEN, ' ')
                return IP(dst=ORCH_IP) / my_proto
            # if response already received
            else:
                info('Recv late data exchange response from %s' % ip_src)
                my_proto.show()
                info('but result already received')
                #  if different host, cancel
                if ip_src != requests[req_id].host:
                    info('Send data exchange cancellation to orchestrator')
                    my_proto.state = DCAN
                    my_proto.host_mac = req[Ether].src
                    my_proto.host_ip = ip_src.ljust(IP_LEN, ' ')
                    return IP(dst=ORCH_IP) / my_proto
                # if same host, acknowledge
                else:
                    info('Send data exchange acknowledgement to orchestrator')
                    my_proto.state = DACK
                    my_proto.host_mac = req[Ether].src
                    my_proto.host_ip = ip_src.ljust(IP_LEN, ' ')
                    return IP(dst=ORCH_IP) / my_proto

        # provider receives data exchange acknowledgement
        if state == DACK and ip_src == ORCH_IP:
            _req_id = (my_proto.src_ip.decode().strip(), req_id)
            if _req_id in _requests and _requests[_req_id].state == DRES:
                info('Recv data exchange acknowledgement from orchestrator')
                my_proto.show()
                if _req_id in _events:
                    _events[_req_id].set()
                # only free resources if still reserved
                if not _requests[_req_id]._freed:
                    info('Freeing resources')
                    free_resources(_requests[_req_id])
                    _requests[_req_id]._freed = True
            return

        # provider receives data exchange cancellation
        if state == DCAN and ip_src == ORCH_IP:
            _req_id = (my_proto.src_ip.decode().strip(), req_id)
            if _req_id in _requests and _requests[_req_id].state == DRES:
                info('Recv data exchange cancellation from orchestrator')
                my_proto.show()
                if _req_id in _events:
                    _events[_req_id].set()
                # only free resources if still reserved
                if not _requests[_req_id]._freed:
                    info('Freeing resources')
                    free_resources(_requests[_req_id])
                    _requests[_req_id]._freed = True

    def _respond_resources(self, my_proto, _req_id):
        my_proto.state = RRES
        retries = PROTO_RETRIES
        rack = None
        while not rack and retries and _requests[_req_id].state == RRES:
            info('Send resource reservation response to orchestrator')
            retries -= 1
            rack = sr1(IP(dst=ORCH_IP) / my_proto,
                       timeout=PROTO_TIMEOUT, verbose=0, iface=IFACE)
        if rack:
            if rack[MyProtocol].state == RCAN:
                info('Recv resource reservation cancellation from orchestrator')
                rack[MyProtocol].show()
                # only free resources if still reserved
                if _requests[_req_id].state == RRES:
                    _requests[_req_id].state = RCAN
                    info('Freeing resources')
                    free_resources(_requests[_req_id])
            else:
                info('Recv resource reservation acknowledgement from '
                     'orchestrator')
                rack[MyProtocol].show()
                _events[_req_id] = Event()
                _events[_req_id].wait(PROTO_RETRIES * PROTO_TIMEOUT)
                if not _events[_req_id].is_set():
                    info('Waiting for data exchange request timed out')
                    info('Freeing resources')
                    free_resources(_requests[_req_id])
                    _requests[_req_id].state = RCAN
                    # info('Send resource reservation cancellation to '
                    #        'orchestrator')
                    # my_proto.state = RCAN
                    # send(IP(dst=ORCH_IP) / my_proto, verbose=0, iface=IFACE)
            return
        # only free resources if still reserved
        elif _requests[_req_id].state == RRES:
            _requests[_req_id].state = RCAN
            info('Waiting for resource reservation acknowledgement timed out')
            info('Freeing resources')
            free_resources(_requests[_req_id])
            info('Send resource reservation cancellation to orchestrator')
            my_proto.state = RCAN
            send(IP(dst=ORCH_IP) / my_proto, verbose=0, iface=IFACE)

    def _respond_data(self, my_proto, ip_src, _req_id):
        info('Executing')
        res = execute(my_proto.data)
        # save result locally
        _requests[_req_id].result = res
        _requests[_req_id].state = DRES
        my_proto.state = DRES
        my_proto.data = res
        retries = PROTO_RETRIES
        _events[_req_id] = Event()
        while retries:
            info('Send data exchange response to %s' % ip_src)
            retries -= 1
            send(IP(dst=ip_src) / my_proto, verbose=0, iface=IFACE)
            _events[_req_id].wait(PROTO_TIMEOUT)
            if _events[_req_id].is_set():
                return
        if not _events[_req_id].is_set():
            info('Waiting for data exchange acknowledgement timed out')
            # only free resources if still reserved
            if not _requests[_req_id]._freed:
                info('Freeing resources')
                free_resources(_requests[_req_id])
                _requests[_req_id]._freed = True


# start the answering machine
AM = MyProtocolAM(verbose=0)
AM(bg=True)


def _generate_request_id():
    id = '_'
    while id in requests:
        id = ''.join(
            choice(ascii_letters + digits) for _ in range(REQ_ID_LEN))
    return id


def send_request(cos_id: int, data: bytes):
    '''
        Send a request to the orchestrator to find a host for a network 
        application of Class of Service (CoS) identified by cos_id, with data 
        as input.

        Returns received result if executed, None if not.
    '''

    req_id = _generate_request_id()
    req = Request(req_id, cos_dict[cos_id], data)
    requests[req_id] = req

    hreq_rt = PROTO_RETRIES
    hres = None

    # dres_at is checked throughout in case of late dres from another host

    while not hres and hreq_rt and not req.dres_at:
        req.host = None
        req.state = HREQ
        attempt = req.new_attempt()
        attempt.state = HREQ
        attempt.hreq_at = time()
        if not req.hreq_at:
            req.hreq_at = attempt.hreq_at
        info('Send host request to orchestrator')
        info(req)
        hreq_rt -= 1
        # send request to orchestrator and wait for response
        hres = srp1(Ether(dst=ORCH_MAC)
                    / IP(dst=ORCH_IP)
                    / MyProtocol(state=HREQ, req_id=req_id, cos_id=req.cos.id,
                                 attempt_no=attempt.attempt_no),
                    timeout=PROTO_TIMEOUT * PROTO_RETRIES, verbose=0, iface=IFACE)
        if hres and not req.dres_at:
            attempt.hres_at = time()
            attempt.state = DREQ
            attempt.host = hres[MyProtocol].host_ip.decode().strip()
            req.state = DREQ
            req.host = attempt.host
            info('Recv host response from orchestrator')
            hres[MyProtocol].show()

            hreq_rt = PROTO_RETRIES
            dreq_rt = PROTO_RETRIES
            dres = None
            while not dres and dreq_rt and not req.dres_at:
                info('Send data exchange request to %s' % req.host)
                info(req)
                dreq_rt -= 1
                # send and wait for response
                host_mac = hres[MyProtocol].host_mac
                dres = srp1(Ether(dst=host_mac)
                            / IP(dst=req.host)
                            / MyProtocol(state=DREQ, req_id=req_id,
                                         attempt_no=attempt.attempt_no,
                                         data=data),
                            timeout=PROTO_TIMEOUT, verbose=0, iface=IFACE)
                if dres and not req.dres_at:
                    # if still executing, wait
                    if dres[MyProtocol].state == DWAIT:
                        dreq_rt = PROTO_RETRIES
                        info('%s still executing' % req_id)
                        _events[req_id] = Event()
                        _events[req_id].wait(PROTO_TIMEOUT)
                        if not _events[req_id].is_set():
                            dres = None
                            continue
                    if dres[MyProtocol].state == DCAN:
                        info('Recv data exchange cancellation from %s' % req.host)
                        dres[MyProtocol].show()
                        # re-send hreq
                        attempt.state = DCAN
                        continue
                    if not req.dres_at:
                        req.dres_at = time()
                        req.state = DRES
                        req.result = dres.data
                        attempt.dres_at = req.dres_at
                        attempt.state = DRES
                        info('Recv data exchange response from %s' % req.host)
                        dres[MyProtocol].show()

                        info('Send data exchange acknowledgement to '
                             'orchestrator')
                        info(req)
                        sendp(Ether(dst=ORCH_MAC)
                              / IP(dst=ORCH_IP)
                              / MyProtocol(state=DACK, req_id=req_id,
                                           host_ip=req.host.ljust(IP_LEN, ' '),
                                           host_mac=host_mac),
                              verbose=0, iface=IFACE)
                    Thread(target=_save, args=(req,)).start()
                    return req.result
                elif not req.dres_at:
                    info('No data')
            hres = None
            if dreq_rt == 0:
                # dres could arrive later
                req._late = True
        elif not req.dres_at:
            info('No hosts')

    if not req.dres_at:
        req.state = FAIL
    info(req)
    Thread(target=_save, args=(req,)).start()
    # if late dres
    if req.dres_at:
        return req.result


def _save(req: Request):
    req.insert()
    for attempt in req.attempts.values():
        attempt.insert()

    # if simulation is active (like mininet), create different CSV files for
    # different hosts (add IP address to file name)
    _suffix = '.' + MY_IP
    Request.as_csv(_suffix=_suffix)
    Attempt.as_csv(_suffix=_suffix)
