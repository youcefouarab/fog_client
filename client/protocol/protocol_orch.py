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
    send_request(cos_id, data): Send a request to the orchestrator to find 
    a host for a network application of Class of Service (CoS) identified by 
    cos_id, with data as input.
'''


# !!IMPORTANT!!
# This module relies on config that is only present AFTER the connect()
# method is called, so only import after


from os import getenv
from threading import Thread, Event
from time import time

from scapy.all import (Packet, ByteEnumField, StrLenField, IntEnumField,
                       StrField, IntField, ConditionalField, AnsweringMachine,
                       bind_layers, send, sendp, srp1, sr1, Ether, IP)

from resources import (check_resources, reserve_resources, free_resources,
                       execute)
from network import MY_IFACE, MY_IP
from common import IS_RESOURCE
from model import Request
from logger import console, file
from utils import all_exit
from settings import *
from consts import *


# decoy controller/orchestrator
ORCH_MAC = getenv('CONTROLLER_DECOY_MAC', None)
if ORCH_MAC == None:
    console.error('CONTROLLER:DECOY_MAC parameter missing from received '
                  'configuration')
    file.error('CONTROLLER:DECOY_MAC parameter missing from received '
               'configuration')
    all_exit()

ORCH_IP = getenv('CONTROLLER_DECOY_IP', None)
if ORCH_IP == None:
    console.error('CONTROLLER:DECOY_IP parameter missing from received '
                  'configuration')
    file.error('CONTROLLER:DECOY_IP parameter missing from received '
               'configuration')
    all_exit()

# dict of data exchange events (keys are (src IP, request ID))
_events = {}


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

    name = PROTO_NAME
    fields_desc = [
        ByteEnumField('state', HREQ, proto_states),
        StrLenField('req_id', '', lambda _: REQ_ID_LEN),
        IntField('attempt_no', 1),
        ConditionalField(IntEnumField('cos_id', 1, cos_names),
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
        return self.req_id

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
    sniff_options = {'filter': 'inbound', 'iface': MY_IFACE}
    send_function = staticmethod(send)
    send_options = {'iface': MY_IFACE}

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
                and req[MyProtocol].req_id)

    def make_reply(self, req):
        my_proto = req[MyProtocol]
        ip_src = req[IP].src
        req_id = my_proto.req_id.decode()
        _req_id = (ip_src, req_id)
        state = my_proto.state
        att_no = my_proto.attempt_no

        _req = requests_.get(_req_id, None)
        my_req = requests.get(req_id, None)
        if my_req:
            att = my_req.attempts.get(att_no, None)

        # provider receives resource reservation request
        if state == RREQ and ip_src == ORCH_IP and IS_RESOURCE:
            ip_src = my_proto.src_ip.decode().strip()
            _req_id = (ip_src, req_id)
            _req = requests_.get(_req_id, None)
            # if new request
            if not _req:
                _req = Request_(req_id)
                _req.state = RREQ
                _req.cos = cos_dict[my_proto.cos_id]
                requests_[_req_id] = _req
            # host request must not have already been reserved
            if _req.state == RREQ or _req.state == RCAN:
                console.info('Recv resource reservation request from '
                             'orchestrator')
                my_proto.show()
                console.info('Reserving resources')
                # if resources are actually reserved
                if reserve_resources(_req):
                    _req.state = RRES
                    _req._freed = False
                # else they became no longer sufficient in time between
                # HREQ and RREQ
                else:
                    console.info('Resources are not sufficient '
                                 '(will exceed limit)')
                    console.info('Send resource reservation cancellation to '
                                 'orchestrator')
                    _req.state = RREQ
                    my_proto.state = RCAN
                    return (IP(dst=ORCH_IP) / my_proto)
            # if resources reserved
            if _req.state == RRES:
                Thread(target=self._respond_resources,
                       args=(my_proto, _req_id, _req), daemon=True).start()
            return

        # provider receives data exchange request
        if state == DREQ and _req:
            if _req_id in _events:
                _events[_req_id].set()
            # already executed
            if _req.state == DRES:
                my_proto.state = DRES
                my_proto.data = _req.result
                return IP(dst=ip_src) / my_proto
            # still executing
            if _req.state == DREQ and _req._thread != None:
                my_proto.state = DWAIT
                return IP(dst=ip_src) / my_proto
            console.info('Recv data exchange request from %s', ip_src)
            my_proto.show()
            # if request was cancelled before
            if _req.state == RCAN:
                # if resources are still available
                if check_resources(_req, quiet=True):
                    console.info('This request arrived late, '
                                 'but resources are still available')
                    console.info('Reserving resources')
                    reserve_resources(_req)
                    _req.state = RRES
                    _req._freed = False
                else:
                    console.info('This request arrived late, '
                                 'and resources are no longer sufficient '
                                 '(will exceed limit)')
                    console.info('Send data exchange cancellation to %s',
                                 ip_src)
                    _req.state = DCAN
                    my_proto.state = DCAN
                    my_proto.src_mac = req[Ether].src
                    my_proto.src_ip = ip_src.ljust(IP_LEN, ' ')
                    my_proto.host_mac = req[Ether].dst
                    my_proto.host_ip = req[IP].dst.ljust(IP_LEN, ' ')
                    return IP(dst=ip_src) / my_proto
            # new execution
            if _req.state == RRES:
                _req.state = DREQ
                th = Thread(
                    target=self._respond_data,
                    args=(my_proto, ip_src, _req_id, _req), daemon=True)
                _req._thread = th
                th.start()
            return

        # consumer receives late data exchange response
        if state == DRES and my_req:
            # if no other response was already accepted
            if not my_req.dres_at:
                dres_at = time()
                my_req.dres_at = dres_at
                my_req.state = DRES
                my_req.host = ip_src
                my_req.result = my_proto.data
                if att:
                    att.state = DRES
                    att.dres_at = dres_at
                console.info('Recv data exchange response from %s', ip_src)
                my_proto.show()
                if req_id in _events:
                    _events[req_id].set()
                console.info('Send data exchange acknowledgement to '
                             'orchestrator')
                my_proto.state = DACK
                my_proto.host_mac = req[Ether].src
                my_proto.host_ip = ip_src.ljust(IP_LEN, ' ')
                return IP(dst=ORCH_IP) / my_proto
            # if response already received
            else:
                console.info('Recv late data exchange response from %s, '
                             'but result already received', ip_src)
                my_proto.show()
                #  if different host, cancel
                if ip_src != my_req.host:
                    console.info('Send data exchange cancellation to '
                                 'orchestrator')
                    my_proto.state = DCAN
                    my_proto.host_mac = req[Ether].src
                    my_proto.host_ip = ip_src.ljust(IP_LEN, ' ')
                    return IP(dst=ORCH_IP) / my_proto
                # if same host, acknowledge
                else:
                    console.info('Send data exchange acknowledgement to '
                                 'orchestrator')
                    my_proto.state = DACK
                    my_proto.host_mac = req[Ether].src
                    my_proto.host_ip = ip_src.ljust(IP_LEN, ' ')
                    return IP(dst=ORCH_IP) / my_proto

        # provider receives data exchange acknowledgement
        if state == DACK and ip_src == ORCH_IP:
            _req_id = (my_proto.src_ip.decode().strip(), req_id)
            if _req_id in requests_ and requests_[_req_id].state == DRES:
                console.info('Recv data exchange acknowledgement from '
                             'orchestrator')
                my_proto.show()
                if _req_id in _events:
                    _events[_req_id].set()
                # only free resources if still reserved
                if not requests_[_req_id]._freed:
                    console.info('Freeing resources')
                    free_resources(requests_[_req_id])
                    requests_[_req_id]._freed = True
            return

        # provider receives data exchange cancellation
        if state == DCAN and ip_src == ORCH_IP:
            ip_src = my_proto.src_ip.decode().strip()
            _req_id = (ip_src, req_id)
            _req = requests_.get(_req_id, None)
            if _req and _req.state == DRES:
                console.info('Recv data exchange cancellation from '
                             'orchestrator')
                my_proto.show()
                if _req_id in _events:
                    _events[_req_id].set()
                # only free resources if still reserved
                if not _req._freed:
                    console.info('Freeing resources')
                    free_resources(_req)
                    _req._freed = True

    def _respond_resources(self, my_proto, _req_id, _req):
        my_proto.state = RRES
        retries = PROTO_RETRIES
        rack = None
        while not rack and retries and _req.state == RRES:
            console.info('Send resource reservation response to orchestrator')
            retries -= 1
            rack = sr1(IP(dst=ORCH_IP) / my_proto,
                       timeout=PROTO_TIMEOUT, verbose=0, iface=MY_IFACE)
        if rack:
            if rack[MyProtocol].state == RCAN:
                console.info('Recv resource reservation cancellation from '
                             'orchestrator')
                rack[MyProtocol].show()
                # only free resources if still reserved
                if _req.state == RRES:
                    _req.state = RCAN
                    console.info('Freeing resources')
                    free_resources(_req)
            else:
                console.info('Recv resource reservation acknowledgement from '
                             'orchestrator')
                rack[MyProtocol].show()
                ev = Event()
                _events[_req_id] = ev
                ev.wait(PROTO_RETRIES * PROTO_TIMEOUT)
                if not ev.is_set():
                    console.info('Waiting for data exchange request timed out')
                    console.info('Freeing resources')
                    free_resources(_req)
                    _req.state = RCAN
                    # console.info('Send resource reservation cancellation to '
                    #              'orchestrator')
                    # my_proto.state = RCAN
                    # send(IP(dst=ORCH_IP) / my_proto, verbose=0, iface=IFACE)
            return
        # only free resources if still reserved
        elif _req.state == RRES:
            _req.state = RCAN
            console.info('Waiting for resource reservation acknowledgement '
                         'timed out')
            console.info('Freeing resources')
            free_resources(_req)
            console.info('Send resource reservation cancellation to '
                         'orchestrator')
            my_proto.state = RCAN
            send(IP(dst=ORCH_IP) / my_proto, verbose=0, iface=MY_IFACE)

    def _respond_data(self, my_proto, ip_src, _req_id, _req):
        console.info('Executing')
        res = execute(my_proto.data)
        # save result locally
        _req.result = res
        _req.state = DRES
        my_proto.state = DRES
        my_proto.data = res
        retries = PROTO_RETRIES
        ev = Event()
        _events[_req_id] = ev
        while retries:
            console.info('Send data exchange response to %s', ip_src)
            retries -= 1
            send(IP(dst=ip_src) / my_proto, verbose=0, iface=MY_IFACE)
            ev.wait(PROTO_TIMEOUT)
            if ev.is_set():
                return
        if not ev.is_set():
            console.info('Waiting for data exchange acknowledgement timed out')
            # only free resources if still reserved
            if not _req._freed:
                console.info('Freeing resources')
                free_resources(_req)
                _req._freed = True


def send_request(cos_id: int, data: bytes):
    '''
        Send a request to the orchestrator to find a host for a network 
        application of Class of Service (CoS) identified by cos_id, with data 
        as input.

        Returns received result if executed, None if not.
    '''

    req_id = gen_req_id()
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
        console.info('Send host request to orchestrator')
        if PROTO_VERBOSE:
            print(req)
        hreq_rt -= 1
        # send request to orchestrator and wait for response
        hres = srp1(Ether(dst=ORCH_MAC)
                    / IP(dst=ORCH_IP)
                    / MyProtocol(state=HREQ, req_id=req_id, cos_id=req.cos.id,
                                 attempt_no=attempt.attempt_no),
                    timeout=PROTO_TIMEOUT * PROTO_RETRIES, verbose=0,
                    iface=MY_IFACE)
        if hres and not req.dres_at:
            attempt.hres_at = time()
            attempt.state = DREQ
            attempt.host = hres[MyProtocol].host_ip.decode().strip()
            req.state = DREQ
            req.host = attempt.host
            console.info('Recv host response from orchestrator')
            hres[MyProtocol].show()

            hreq_rt = PROTO_RETRIES
            dreq_rt = PROTO_RETRIES
            dres = None
            while not dres and dreq_rt and not req.dres_at:
                console.info('Send data exchange request to %s', req.host)
                if PROTO_VERBOSE:
                    print(req)
                dreq_rt -= 1
                # send and wait for response
                host_mac = hres[MyProtocol].host_mac
                dres = srp1(Ether(dst=host_mac)
                            / IP(dst=req.host)
                            / MyProtocol(state=DREQ, req_id=req_id,
                                         attempt_no=attempt.attempt_no,
                                         data=data),
                            timeout=PROTO_TIMEOUT, verbose=0, iface=MY_IFACE)
                if dres and not req.dres_at:
                    # if still executing, wait
                    if dres[MyProtocol].state == DWAIT:
                        dreq_rt = PROTO_RETRIES
                        console.info('%s still executing', req_id)
                        _events[req_id] = Event()
                        _events[req_id].wait(PROTO_TIMEOUT)
                        if not _events[req_id].is_set():
                            dres = None
                            continue
                    if dres[MyProtocol].state == DCAN:
                        console.info(
                            'Recv data exchange cancellation from %s',
                            req.host)
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
                        console.info('Recv data exchange response from %s',
                                     req.host)
                        dres[MyProtocol].show()

                        console.info('Send data exchange acknowledgement to '
                                     'orchestrator')
                        if PROTO_VERBOSE:
                            print(req)
                        sendp(Ether(dst=ORCH_MAC)
                              / IP(dst=ORCH_IP)
                              / MyProtocol(state=DACK, req_id=req_id,
                                           host_ip=req.host.ljust(IP_LEN, ' '),
                                           host_mac=host_mac),
                              verbose=0, iface=MY_IFACE)
                    Thread(target=save_req, args=(req,), daemon=True).start()
                    return req.result
                elif not req.dres_at:
                    console.info('No data')
            hres = None
            if dreq_rt == 0:
                # dres could arrive later
                req._late = True
        elif not req.dres_at:
            console.info('No hosts')

    if not req.dres_at:
        req.state = FAIL
    if PROTO_VERBOSE:
        print(req)
    Thread(target=save_req, args=(req,), daemon=True).start()
    # if late dres
    if req.dres_at:
        return req.result
