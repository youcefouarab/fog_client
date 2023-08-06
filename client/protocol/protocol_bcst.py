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


# !!IMPORTANT!!
# This module relies on config that is only present AFTER the connect()
# method is called, so only import after


from threading import Thread
from time import time
from logging import info

from scapy.all import (Packet, ByteEnumField, StrLenField, IntEnumField,
                       StrField, IntField, IEEEDoubleField, ConditionalField,
                       AnsweringMachine, conf, bind_layers, send, srp1, sr1,
                       sniff, Ether, IP)

from simulator import (get_resources, check_resources, reserve_resources,
                       free_resources, execute)
from model import Request, Response
from network import MY_IFACE, MY_IP, BROADCAST_IP
from common import IS_RESOURCE
from settings import *
from consts import *


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
        (6) (resource reservation cancellation), DREQ (7) (data exchange 
        request), DRES (8) (data exchange response), DACK (9) (data exchange 
        acknowledgement), DCAN (10) (data exchange cancellation), DWAIT (11) 
        (data exchange wait). Default is HREQ (1).

        req_id: String of 10 bytes indicating the request's ID. Default is ''.

        attempt_no: Integer of 4 bytes indicating the attempt number. Default 
        is 1. 

        cos_id: Integer of 4 bytes indicating the application's CoS ID. Default 
        is 1 (best-effort). Conditional field for state == HREQ (1).

        data: String of undefined number of bytes containing input data and 
        possibly program to execute. Default is ''. Conditional field for 
        state == DREQ (6) or state == DRES (7).

        cpu_offer: IEEE double of 8 bytes indicating the amount of CPU offered 
        by the responding host. Default is 0. Conditional field for 
        state == HRES (2).

        ram_offer: IEEE double of 8 bytes indicating the size of RAM offered by
        the responding host. Default is 0. Conditional field for 
        state == HRES (2).

        disk_offer: IEEE double of 8 bytes indicating the size of disk offered 
        by the responding host. Default is 0. Conditional field for 
        state == HRES (2).
    '''

    name = PROTO_NAME
    fields_desc = [
        ByteEnumField('state', HREQ, proto_states),
        StrLenField('req_id', '', lambda _: REQ_ID_LEN),
        IntField('attempt_no', 1),
        ConditionalField(IntEnumField('cos_id', 1, cos_names),
                         lambda pkt: pkt.state == HREQ),
        ConditionalField(StrField('data', ''),
                         lambda pkt: pkt.state == DREQ or pkt.state == DRES),
        ConditionalField(IEEEDoubleField('cpu_offer', 0),
                         lambda pkt: pkt.state == HRES),
        ConditionalField(IEEEDoubleField('ram_offer', 0),
                         lambda pkt: pkt.state == HRES),
        ConditionalField(IEEEDoubleField('disk_offer', 0),
                         lambda pkt: pkt.state == HRES),
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
                                             or self.state == DCAN))):
            return 1
        return 0


# for scapy to be able to dissect MyProtocol packets
bind_layers(Ether, MyProtocol)
bind_layers(IP, MyProtocol)

# IP broadcast fails when the following are true (responses are not received)
conf.checkIPaddr = False
conf.checkIPsrc = False
# making them false means IP src must be checked manually


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

        # provider receives host request
        if state == HREQ and IS_RESOURCE:
            # if new request
            if not _req:
                _req = Request_(req_id)
                _req.state = HREQ
                requests_[_req_id] = _req
            # if not old request that was cancelled
            if _req.state in (HREQ, HRES):
                info('Recv host request from %s' % ip_src)
                my_proto.show()
                # set cos (for new requests and in case CoS was changed for
                # old request)
                _req.cos = cos_dict[my_proto.cos_id]
                info('Checking resources')
                cpu, ram, disk = get_resources()
                check = check_resources(_req)
                if check:
                    info('Send host response to %s' % ip_src)
                    _req.state = HRES
                    my_proto.state = HRES
                    my_proto.cpu_offer = cpu
                    my_proto.ram_offer = ram
                    my_proto.disk_offer = disk
                    return IP(dst=ip_src) / my_proto
                else:
                    info('Insufficient (will exceed limit)')
                    _req.state = HREQ
            return

        # consumer receives host responses (save in database)
        # if request has not been already answered or failed
        if state == HRES and my_req and my_req.state not in (DRES, FAIL):
            my_req.attempts[att_no].responses[ip_src] = Response(
                req_id, att_no, ip_src, my_proto.cpu_offer, my_proto.ram_offer,
                my_proto.disk_offer)
            return

        # provider receives resource reservation request
        if state == RREQ and _req:
            # host request must have already been answered positively
            # but not yet reserved
            if _req.state == HRES:
                info('Recv resource reservation request from %s' % ip_src)
                my_proto.show()
                info('Reserving resources')
                # if resources are actually reserved
                if reserve_resources(_req):
                    _req.state = RRES
                    _req._freed = False
                # else they became no longer sufficient in time between
                # HRES and RREQ
                else:
                    info('Resources are no longer sufficient '
                         '(will exceed limit)\n'
                         'Send resource reservation cancellation to %s'
                         % ip_src)
                    _req.state = HREQ
                    my_proto.state = RCAN
                    return IP(dst=ip_src) / my_proto
            # if resources reserved
            if _req.state == RRES:
                Thread(target=self._respond_resources,
                       args=(my_proto, ip_src, _req)).start()
            return

        # consumer receives late resource reservation response
        # from a previous host
        if state == RRES and my_req and ip_src != req.host:
            info('Recv late resource reservation response from %s' % ip_src)
            my_proto.show()
            # cancel with previous host
            info('Send resource reservation cancellation to %s' % ip_src)
            my_proto.state = RCAN
            return IP(dst=ip_src) / my_proto

        # provider receives data exchange request
        if state == DREQ and _req:
            # already executed
            if _req.state == DRES:
                my_proto.state = DRES
                my_proto.data = _req.result
                return IP(dst=ip_src) / my_proto
            # still executing
            if _req.state == RRES and _req._thread != None:
                my_proto.state = DWAIT
                return IP(dst=ip_src) / my_proto
            info('Recv data exchange request from %s' % ip_src)
            my_proto.show()
            # if request was cancelled before
            if _req.state == HREQ:
                info('This request arrived late')
                # if resources are still available
                if check_resources(_req, quiet=True):
                    info('but resources are still available\n'
                         'Reserving resources')
                    reserve_resources(_req)
                    _req.state = RRES
                    _req._freed = False
                else:
                    info('and resources are no longer sufficient '
                         '(will exceed limit)\n'
                         'Send data exchange cancellation to %s' % ip_src)
                    _req.state = HREQ
                    my_proto.state = DCAN
                    return IP(dst=ip_src) / my_proto
            # new execution
            if _req.state == RRES:
                th = Thread(target=self._respond_data,
                            args=(my_proto, ip_src, _req))
                _req._thread = th
                th.start()
            return

        # consumer receives late data exchange response
        if state == DRES and my_req:
            # if no other response was already accepted
            if not my_req.dres_at:
                #  if response from previous host, accept
                if ip_src != my_req.host and my_req._late:
                    dres_at = time()
                    my_req.dres_at = dres_at
                    my_req.state = DRES
                    my_req.host = ip_src
                    my_req.result = my_proto.data
                    if att:
                        att.state = DRES
                        att.dres_at = dres_at
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
                if ip_src != my_req.host:
                    info('Send data exchange cancellation to %s' % ip_src)
                    my_proto.state = DCAN
                # if same host, acknowledge
                else:
                    info('Send data exchange acknowledgement to %s' % ip_src)
                    my_proto.state = DACK
                return IP(dst=ip_src) / my_proto

        # provider receives data exchange acknowledgement
        if state == DACK and _req and _req.state == DRES:
            info('Recv data exchange acknowledgement from %s' % ip_src)
            my_proto.show()
            # only free resources if still reserved
            if not _req._freed:
                info('Freeing resources')
                free_resources(_req)
                _req._freed = True

    def _respond_resources(self, my_proto, ip_src, _req):
        my_proto.state = RRES
        retries = PROTO_RETRIES
        dreq = None
        while not dreq and retries and _req.state == RRES:
            info('Send resource reservation response to %s' % ip_src)
            retries -= 1
            dreq = sr1(IP(dst=ip_src) / my_proto,
                       timeout=PROTO_TIMEOUT, verbose=0, iface=MY_IFACE)
            if dreq and dreq[MyProtocol].state == RCAN:
                info('Recv resource reservation cancellation from %s' % ip_src)
                my_proto.show()
                _req.state = HREQ
                info('Freeing resources')
                free_resources(_req)
                return
        # only free resources if still reserved
        if not dreq and _req.state == RRES:
            info('Waiting for data exchange request timed out')
            info('Freeing resources')
            free_resources(_req)
            _req.state = HREQ
            my_proto.state = RCAN
            send(IP(dst=ip_src) / my_proto, verbose=0, iface=MY_IFACE)

    def _respond_data(self, my_proto, ip_src, _req):
        info('Executing')
        res = execute(my_proto.data)
        # save result locally
        _req.result = res
        _req.state = DRES
        my_proto.state = DRES
        my_proto.data = res
        retries = PROTO_RETRIES
        dack = None
        while not dack and retries:
            info('Send data exchange response to %s' % ip_src)
            retries -= 1
            dack = sr1(IP(dst=ip_src) / my_proto,
                       timeout=PROTO_TIMEOUT, verbose=0, iface=MY_IFACE)
            if dack and dack[MyProtocol].state == DCAN:
                info('Recv data exchange cancellation from %s' % ip_src)
                # only free resources if still reserved
                if not _req._freed:
                    info('Freeing resources')
                    free_resources(_req)
                    _req._freed = True
                    return
        if not dack:
            info('Waiting for data exchange acknowledgement timed out')
            # only free resources if still reserved
            if not _req._freed:
                info('Freeing resources')
                free_resources(_req)
                _req._freed = True


def send_request(cos_id: int, data: bytes):
    '''
        Broadcast a request to host a network application of Class of Service 
        (CoS) identified by cos_id, with data as input.
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
        info('Broadcasting host request')
        info(req)
        hreq_rt -= 1
        # send broadcast and wait for first response
        hres = srp1(Ether(dst=BROADCAST_MAC)
                    / IP(dst=BROADCAST_IP)
                    / MyProtocol(state=HREQ, req_id=req_id, cos_id=req.cos.id,
                                 attempt_no=attempt.attempt_no),
                    timeout=PROTO_TIMEOUT, verbose=0, iface=MY_IFACE)
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
                           timeout=PROTO_TIMEOUT, verbose=0, iface=MY_IFACE)
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
                                filter='inbound', count=1, iface=MY_IFACE,
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
                                   timeout=PROTO_TIMEOUT, verbose=0, iface=MY_IFACE)
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
                                        filter='inbound', count=1, iface=MY_IFACE,
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
                                     verbose=0, iface=MY_IFACE)
                            Thread(target=save_req, args=(req,)).start()
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
    Thread(target=save_req, args=(req,)).start()
    # if late dres
    if req.dres_at:
        return req.result
