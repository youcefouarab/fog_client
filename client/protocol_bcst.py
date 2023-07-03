'''
    Definition of the communication protocol between hosts in BROADCAST (BCST)
    mode, including the packets' header and the protocol's responder, using 
    the library Scapy.

    Classes:
    --------
    MyProtocol: Class deriving from Scapy's Packet class to define the 
    communication protocol between hosts in BROADCAST (BCST) mode, including 
    the packet header's fields, as well as ways to detect if a packet is an 
    answer to another.

    MyProtocolAM: Class deriving from Scapy's AnsweringMachine class to define 
    the protocol's responder, which takes decisions and builds and sends 
    replies to received packets based on the protocol's state.

    Methods:
    --------
    send_request(cos_id, data): Broadcast a request to host a network 
    application of Class of Service (CoS) identified by cos_id, with data as 
    input.
'''


from os import getenv
from threading import Thread
from time import time
from string import ascii_letters, digits
from random import choice
from logging import info, basicConfig, INFO, root

from scapy.all import (Packet, ByteEnumField, StrLenField, IntEnumField,
                       StrField, IntField, IEEEDoubleField, ConditionalField,
                       AnsweringMachine, conf, bind_layers, send, srp1, sr1,
                       sniff, Ether, IP)

from simulator import (get_resources, check_resources, reserve_resources,
                       free_resources, execute)
from model import CoS, Request, Attempt, Response
from common import *


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

PROTO_VERBOSE = getenv('PROTOCOL_VERBOSE', False) == 'True'

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

# dict of responses received by consumer (keys are request IDs)
_responses = {}


class _Request(Request):
    def __init__(self, id):
        super().__init__(id, None, None)
        self._thread = None
        self._freed = True


class MyProtocol(Packet):
    '''
        Class deriving from Scapy's Packet class to define the communication 
        protocol between hosts in BROADCAST (BCST) mode, including the packet 
        header's fields, as well as ways to detect if a packet is an answer 
        to another.

        Fields:
        -------
        state: 1 byte indicating the state of the protocol, enumeration of 
        HREQ (1) (host request), HRES (2) (host response), RREQ (3) (resource 
        reservation request), RRES (4) (resource reservation response), RCAN 
        (5) (resource reservation cancellation), DREQ (6) (data exchange 
        request), DRES (7) (data exchange response), DACK (8) (data exchange 
        acknowledgement), DCAN (9) (data exchange cancellation), DWAIT (10) 
        (data exchange wait). Default is HREQ (1).

        req_id: String of 10 bytes indicating the request's ID. Default is ''.

        attempt_no: Integer of 4 bytes indicating the attempt number. Default 
        is 1. 

        cos_id: Integer of 4 bytes indicating the application's CoS ID. Default 
        is 1 (best-effort). Conditional field for state == HREQ (1).

        data: String of undefined number of bytes containing input data and 
        possibly program to execute. Default is ''. Conditional field for 
        state == DREQ (6) or state == DRES (7).

        cpu_offer: Integer of 4 bytes indicating the number of CPUs offered by
        the responding host. Default is 0. Conditional field for 
        state == HRES (2).

        ram_offer: IEEE double of 8 bytes indicating the size of RAM offered by
        the responding host. Default is 0. Conditional field for 
        state == HRES (2).

        disk_offer: IEEE double of 8 bytes indicating the size of disk offered 
        by the responding host. Default is 0. Conditional field for 
        state == HRES (2).
    '''

    _states = {
        HREQ: 'host request (HREQ)',
        HRES: 'host response (HRES)',
        RREQ: 'resource reservation request (RREQ)',
        RRES: 'resource reservation response (RRES)',
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
                         lambda pkt: pkt.state == HREQ),
        ConditionalField(StrField('data', ''),
                         lambda pkt: pkt.state == DREQ or pkt.state == DRES),
        ConditionalField(IntField('cpu_offer', 0),
                         lambda pkt: pkt.state == HRES),
        ConditionalField(IEEEDoubleField('ram_offer', 0),
                         lambda pkt: pkt.state == HRES),
        ConditionalField(IEEEDoubleField('disk_offer', 0),
                         lambda pkt: pkt.state == HRES),
    ]

    def show(self):
        if root.level == INFO:
            print()
            return super().show()

    def hashret(self):
        return self.req_id + str(self.attempt_no).encode()

    def answers(self, other):
        if not isinstance(other, MyProtocol):
            return 0
        # host request expects host response
        if (other.state == HREQ and self.state == HRES
            # resource reservation request expects resource reservation
            # response or resource reservation cancellation
            or other.state == RREQ and (self.state == RRES
                                        or self.state == RCAN)
            # resource reservation response expects data exchange request
            # or resource reservation cancellation
            or other.state == RRES and (self.state == DREQ
                                        or self.state == RCAN)
            # data exchange request expects data exchange response, data
            # exchange wait, or data exchange cancellation
            or other.state == DREQ and (self.state == DRES
                                        or self.state == DWAIT
                                        or self.state == DCAN)
            # data exchange response expects data exchange acknowledgement
            # or data exchange cancellation
            or other.state == DRES and (self.state == DACK
                                        or self.state == DCAN)):
            return 1
        return 0


# for scapy to be able to dissect MyProtocol packets
# bind_layers(Ether, MyProtocol)
bind_layers(IP, MyProtocol)

# IP broadcast fails when the following are true (responses are not received)
conf.checkIPaddr = False
conf.checkIPsrc = False
# making them false means IP src must be checked manually


class MyProtocolAM(AnsweringMachine):
    '''
        This class defines the protocol's responder (Answering Machine), which 
        takes decisions and builds and sends replies to received packets based 
        on the protocol's state.
    '''

    function_name = 'mpam'
    sniff_options = {'filter': 'inbound'}
    send_function = staticmethod(send)

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
                and req[MyProtocol].req_id != '')

    def make_reply(self, req):
        my_proto = req[MyProtocol]
        ip_src = req[IP].src
        req_id = my_proto.req_id.decode()
        _req_id = (ip_src, req_id)
        state = my_proto.state

        # provider receives host request
        if state == HREQ:
            # if new request
            if _req_id not in _requests:
                _requests[_req_id] = _Request(req_id)
                _requests[_req_id].state = HREQ
            # if not old request that was cancelled
            if (_requests[_req_id].state == HREQ
                    or _requests[_req_id].state == HRES):
                info('Recv host request from %s' % ip_src)
                my_proto.show()
                # set cos (for new requests and in case CoS was changed for
                # old request)
                _requests[_req_id].cos = cos_dict[my_proto.cos_id]
                info('Checking resources')
                cpu, ram, disk, _, _ = get_resources(_requests[_req_id])
                check = check_resources(_requests[_req_id])
                if check:
                    info('Send host response to %s' % ip_src)
                    _requests[_req_id].state = HRES
                    my_proto.state = HRES
                    my_proto.cpu_offer = cpu
                    my_proto.ram_offer = ram
                    my_proto.disk_offer = disk
                    return IP(dst=ip_src) / my_proto
                else:
                    info('Insufficient')
                    _requests[_req_id].state = HREQ
            return

        # consumer receives host responses (save in database)
        if (state == HRES and req_id in requests
                # if request has not been already answered
                and requests[req_id].state != DRES
                # or already failed
                and requests[req_id].state != FAIL):
            _responses.setdefault(req_id, [])
            _responses[req_id].append(Response(req_id, my_proto.attempt_no,
                                               ip_src, my_proto.cpu_offer,
                                               my_proto.ram_offer,
                                               my_proto.disk_offer))
            return

        # provider receives resource reservation request
        if state == RREQ and _req_id in _requests:
            # host request must have already been answered positively
            # but not yet reserved
            if _requests[_req_id].state == HRES:
                info('Recv resource reservation request from %s' % ip_src)
                my_proto.show()
                info('Reserving resources')
                # if resources are actually reserved
                if reserve_resources(_requests[_req_id]):
                    _requests[_req_id].state = RRES
                    _requests[_req_id]._freed = False
                # else they became no longer sufficient in time between
                # HREQ and RREQ
                else:
                    info('Resources are no longer sufficient')
                    info('Send resource reservation cancellation to %s' % ip_src)
                    _requests[_req_id].state = HREQ
                    my_proto.state = RCAN
                    return IP(dst=ip_src) / my_proto
            # if resources reserved
            if _requests[_req_id].state == RRES:
                Thread(target=self._respond_resources,
                       args=(my_proto, ip_src,)).start()
            return

        # consumer receives late resource reservation response
        if (state == RRES and req_id in requests
                # from a previous host
                and ip_src != requests[req_id].host):
            info('Recv late resource reservation response from %s' % ip_src)
            my_proto.show()
            # cancel with previous host
            info('Send resource reservation cancellation to %s' % ip_src)
            my_proto.state = RCAN
            return IP(dst=ip_src) / my_proto

        # provider receives data exchange request
        if state == DREQ and _req_id in _requests:
            # already executed
            if _requests[_req_id].state == DRES:
                my_proto.state = DRES
                my_proto.data = _requests[_req_id].result
                return IP(dst=ip_src) / my_proto
            # still executing
            if (_requests[_req_id].state == RRES
                    and _requests[_req_id]._thread != None):
                my_proto.state = DWAIT
                return IP(dst=ip_src) / my_proto
            info('Recv data exchange request from %s' % ip_src)
            my_proto.show()
            # if request was cancelled before
            if _requests[_req_id].state == HREQ:
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
                    _requests[_req_id].state = HREQ
                    my_proto.state = DCAN
                    return IP(dst=ip_src) / my_proto
            # new execution
            if _requests[_req_id].state == RRES:
                th = Thread(target=self._respond_data,
                            args=(my_proto, ip_src,))
                _requests[_req_id]._thread = th
                th.start()
            return

        # consumer receives late data exchange response
        if state == DRES and req_id in requests:
            # if no other response was already accepted
            if not requests[req_id].dres_at:
                #  if response from previous host, accept
                if ip_src != requests[req_id].host and requests[req_id]._late:
                    requests[req_id].dres_at = time()
                    requests[req_id].state = DRES
                    requests[req_id].host = ip_src
                    requests[req_id].result = my_proto.data
                    requests[req_id].attempts[my_proto.attempt_no].state = DRES
                    requests[req_id].attempts[my_proto.attempt_no].dres_at = (
                        requests[req_id].dres_at)
                    info('Recv late data exchange response from %s' % ip_src)
                    my_proto.show()
                    info('Send data exchange acknowledgement to %s' % ip_src)
                    my_proto.state = DACK
                    return IP(dst=ip_src) / my_proto
                return
            # if response already received
            else:
                info('Recv late data exchange response from %s' % ip_src)
                my_proto.show()
                info('but result already received')
                #  if different host, cancel
                if ip_src != requests[req_id].host:
                    info('Send data exchange cancellation to %s' % ip_src)
                    my_proto.state = DCAN
                # if same host, acknowledge
                else:
                    info('Send data exchange acknowledgement to %s' % ip_src)
                    my_proto.state = DACK
                return IP(dst=ip_src) / my_proto

        # provider receives data exchange acknowledgement
        if (state == DACK and _req_id in _requests
                and _requests[_req_id].state == DRES):
            info('Recv data exchange acknowledgement from %s' % ip_src)
            my_proto.show()
            # only free resources if still reserved
            if not _requests[_req_id]._freed:
                info('Freeing resources')
                free_resources(_requests[_req_id])
                _requests[_req_id]._freed = True

    def _respond_resources(self, my_proto, ip_src):
        _req_id = (ip_src, my_proto.req_id.decode())
        my_proto.state = RRES
        retries = PROTO_RETRIES
        dreq = None
        while not dreq and retries and _requests[_req_id].state == RRES:
            info('Send resource reservation response to %s' % ip_src)
            retries -= 1
            dreq = sr1(IP(dst=ip_src) / my_proto,
                       timeout=PROTO_TIMEOUT, verbose=0)
            if dreq and dreq[MyProtocol].state == RCAN:
                info('Recv resource reservation cancellation from %s' % ip_src)
                my_proto.show()
                _requests[_req_id].state = HREQ
                info('Freeing resources')
                free_resources(_requests[_req_id])
                return
        # only free resources if still reserved
        if not dreq and _requests[_req_id].state == RRES:
            info('Waiting for data exchange request timed out')
            info('Freeing resources')
            free_resources(_requests[_req_id])
            _requests[_req_id].state = HREQ
            my_proto.state = RCAN
            send(IP(dst=ip_src) / my_proto, verbose=0)

    def _respond_data(self, my_proto, ip_src):
        info('Executing')
        res = execute(my_proto.data)
        _req_id = (ip_src, my_proto.req_id.decode())
        # save result locally
        _requests[_req_id].result = res
        _requests[_req_id].state = DRES
        my_proto.state = DRES
        my_proto.data = res
        retries = PROTO_RETRIES
        dack = None
        while not dack and retries:
            info('Send data exchange response to %s' % ip_src)
            retries -= 1
            dack = sr1(IP(dst=ip_src) / my_proto,
                       timeout=PROTO_TIMEOUT, verbose=0)
            if dack and dack[MyProtocol].state == DCAN:
                info('Recv data exchange cancellation from %s' % ip_src)
                # only free resources if still reserved
                if not _requests[_req_id]._freed:
                    info('Freeing resources')
                    free_resources(_requests[_req_id])
                    _requests[_req_id]._freed = True
                    return
        if not dack:
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
        Broadcast a request to host a network application of Class of Service 
        (CoS) identified by cos_id, with data as input.
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
        info('Send host request')
        info(req)
        hreq_rt -= 1
        # send broadcast and wait for first response
        hres = srp1(Ether(dst=BROADCAST_MAC)
                    / IP(dst=BROADCAST_IP)
                    / MyProtocol(state=HREQ, req_id=req_id, cos_id=req.cos.id,
                                 attempt_no=attempt.attempt_no),
                    timeout=PROTO_TIMEOUT, verbose=0)
        if hres and not req.dres_at:
            attempt.hres_at = time()
            attempt.state = RREQ
            req.state = RREQ
            req.host = hres[IP].src
            attempt.host = req.host
            info('Recv first host response from %s' % req.host)
            hres[MyProtocol].show()

            hreq_rt = PROTO_RETRIES
            rreq_rt = PROTO_RETRIES
            rres = None
            while not rres and rreq_rt and not req.dres_at:
                info('Send resource reservation request to %s' % req.host)
                info(req)
                rreq_rt -= 1
                # send and wait for response
                rres = sr1(IP(dst=req.host)
                           / MyProtocol(state=RREQ, req_id=req_id),
                           timeout=PROTO_TIMEOUT, verbose=0)
                if rres and not req.dres_at:
                    # if late response from previous host
                    # cancel (in MyProtocolAM)
                    # and wait for rres from current host
                    if rres[IP].src != req.host:
                        try:
                            rres = sniff(
                                lfilter=(lambda pkt: (
                                    IP in pkt
                                    and pkt[IP].src == req.host
                                    and MyProtocol in pkt
                                    and pkt[MyProtocol].req_id == req_id
                                    and (pkt[MyProtocol].state == RRES
                                         or pkt[MyProtocol].state == RCAN))),
                                filter='inbound', count=1,
                                timeout=PROTO_TIMEOUT)[0]
                        except:
                            rres = None
                            continue
                    # if cancelled from provider (maybe resources became no
                    # longer sufficient between hres and rreq)
                    if rres[MyProtocol].state == RCAN:
                        info('Recv resource reservation cancellation from',
                             req.host)
                        rres[MyProtocol].show()
                        # re-send hreq
                        attempt.state = RCAN
                        continue
                    attempt.rres_at = time()
                    attempt.state = DREQ
                    req.state = DREQ
                    info('Recv resource reservation response from %s' % req.host)
                    rres[MyProtocol].show()

                    dreq_rt = PROTO_RETRIES
                    dres = None
                    while not dres and dreq_rt and not req.dres_at:
                        info('Send data exchange request to %s' % req.host)
                        info(req)
                        dreq_rt -= 1
                        # send and wait for response
                        dres = sr1(IP(dst=req.host)
                                   / MyProtocol(state=DREQ, req_id=req_id,
                                                attempt_no=attempt.attempt_no,
                                                data=data),
                                   timeout=PROTO_TIMEOUT, verbose=0)
                        if dres and not req.dres_at:
                            # if still executing, wait
                            if (dres[IP].src == req.host
                                    and dres[MyProtocol].state == DWAIT):
                                dreq_rt = PROTO_RETRIES
                                info(req_id, 'still executing')
                            # if response from previous host
                            # let MyProtocolAM handle it
                            if dres[IP].src != req.host:
                                dreq_rt += 1
                            if (dres[IP].src != req.host
                                or (dres[IP].src == req.host
                                    and dres[MyProtocol].state == DWAIT)):
                                try:
                                    # while waiting, sniff for dres
                                    dres = sniff(
                                        lfilter=(lambda pkt: (
                                            IP in pkt
                                            and pkt[IP].src == req.host
                                            and MyProtocol in pkt
                                            and pkt[MyProtocol].req_id == req_id
                                            and pkt[MyProtocol].state == DRES)),
                                        filter='inbound', count=1,
                                        timeout=PROTO_TIMEOUT)[0]
                                except:
                                    dres = None
                                    continue
                            if dres[MyProtocol].state == DCAN:
                                info(
                                    'Recv data exchange cancellation from %s' % req.host)
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
                                info('Recv data exchange response from %s' %
                                     req.host)
                                dres[MyProtocol].show()
                                info(
                                    'Send data exchange acknowledgement to %s' % req.host)
                                info(req)
                                send(IP(dst=req.host)
                                     / MyProtocol(state=DACK, req_id=req_id),
                                     verbose=0)
                            Thread(target=_save, args=(req,)).start()
                            return req.result
                        elif not req.dres_at:
                            info('No data')
                    hres = None
                    if dreq_rt == 0:
                        # dres could arrive later
                        req._late = True
                elif not req.dres_at:
                    info('No resources')
            hres = None
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
    if req.id in _responses:
        for response in _responses[req.id]:
            response.insert()

    # if simulation is active (like mininet), create different CSV files for
    # different hosts (add IP address to file name)
    _suffix = '.' + MY_IP
    Request.as_csv(_suffix=_suffix)
    Attempt.as_csv(_suffix=_suffix)
    Response.as_csv(_suffix=_suffix)
