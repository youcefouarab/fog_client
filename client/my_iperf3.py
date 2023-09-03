# !!IMPORTANT!!
# This module relies on config that is only present AFTER the connect()
# method is called, so only import after


from os import getenv
from threading import Thread, Event
from time import sleep

from iperf3 import Server, Client

from model import Node
from api import get_iperf3_target
from utils import port_open
from logger import console, file


IPERF3_MODE = getenv('IPERF3_MODE', None)
IPERF3_SERVER_PORT = 5201

# if trouble with detecting if port is open (servers restarting on their own)
# increase the sleep time after port check to reduce possible overflow
PORT_CHECK_SLEEP = 0.1

servers = {}
iperf3_measures = {}
iperf3_enabled = False


def launch_iperf3(node: Node, listeners: list):
    if IPERF3_MODE in ('server', 'client', 'dual'):
        global iperf3_enabled
        iperf3_enabled = True
        console.info('Please wait for iPerf3 to finish...')

    if IPERF3_MODE in ('server', 'dual'):
        event = Event()
        Thread(target=_server_run, args=(node, listeners, event,),
               daemon=True).start()
        event.wait()

    if IPERF3_MODE in ('client', 'dual'):
        global iperf3_measures
        for name, iface in node.interfaces.items():
            target, *_ = get_iperf3_target(node, iface)
            if target:
                client = Client()
                client.duration = 1
                client.verbose = False
                client.zerocopy = True
                client.server_hostname = target['ip']
                try:
                    result = client.run()
                    # IMPORTANT to close client and free stdout
                    client = None
                    iperf3_measures.setdefault(name, {})
                    iperf3_measures[name]['sent_bps'] = result.sent_bps
                    iperf3_measures[name]['received_bps'] = result.received_bps
                    # to avoid overflow
                    # sleep(1)
                except:
                    console.error('iPerf3 client error on %s', name)
                    file.exception('iPerf3 client error on %s', name)


def _server_run(node: Node, listeners: list, event: Event):
    def _run(server: Server):
        server.verbose = False
        while True:
            try:
                server.run()
            except:
                file.exception('iPerf3 server error on %s',
                               server.bind_address)

    def _create(bind_address):
        server = Server()
        server.bind_address = bind_address
        return server

    global servers
    while True:
        # keep servers running (i.e. if server down detected, re-run)
        for name, iface in node.interfaces.items():
            _iperf3_ip = iface._iperf3_ip
            if name in listeners and _iperf3_ip:
                if _iperf3_ip not in servers:
                    if port_open(_iperf3_ip, IPERF3_SERVER_PORT):
                        # already opened by another server
                        servers[_iperf3_ip] = None
                    else:
                        # start server
                        server = _create(_iperf3_ip)
                        servers[_iperf3_ip] = server
                        Thread(target=_run, args=(server,),
                               daemon=True).start()
                    # sleep after successive port_open because connection
                    # could fail due to temporary overflow
                    sleep(PORT_CHECK_SLEEP)
                else:
                    if not servers[_iperf3_ip]:
                        if not port_open(_iperf3_ip, IPERF3_SERVER_PORT):
                            # closed by the other server
                            # restart server
                            server = _create(_iperf3_ip)
                            servers[_iperf3_ip] = server
                            Thread(target=_run, args=(server,),
                                   daemon=True).start()
                        sleep(PORT_CHECK_SLEEP)
        event.set()
        # re-check servers periodically
        sleep(1)
