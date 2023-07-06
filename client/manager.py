from os import environ, getenv
from threading import Thread
from time import sleep
from psutil import net_if_addrs
from socket import socket, AF_INET, AF_PACKET, SOCK_DGRAM, gethostname
from re import findall
from uuid import getnode

from model import Node, NodeType, Interface
from consts import *


class Manager:
    '''
        Class for managing multiple aspects of the client component, such as 
        building the Node and Interface models, managing the connection to the 
        orchestrator, and sending node and/or network specs periodically 
        (depending on the mode).

        Attributes:
        -----------
        node: Custom Node object (useful for simulations and/or testing). Not 
        required; by default, the Node object is automatically built from the 
        node's real data. 

        verbose: If True, a detailed output will be produced on the console.

        Methods:
        --------
        connect(mode, **kwargs): Request the joining of the node in the 
        orchestrated topology in one of three modes: client, resource, or 
        switch.

        disconnect(): Request the withdrawal of the node from the orchestrated 
        topology.
    '''

    def __init__(self, node: Node = None, verbose: bool = False):
        self.node = node
        self.verbose = verbose

        self._connected = False

    def connect(self, mode: str, **kwargs):
        '''
            Request the joining of the node in the orchestrated topology in one 
            of three modes: client, resource, or switch.

            Client mode means the node participates in the orchestration but 
            only to request resources; it has no resources of its own to offer.

            Resource mode includes client mode, but the node also offers its 
            resources for use by other clients and resources.

            If the mode is 'client' or 'resource', it is possible to specify a 
            custom node ID and/or label through 'id' and 'label' kwargs 
            respectively (this is useful, and sometimes necessary to avoid 
            conflicts, in simulations and/or emulations like Mininet).

            Switch mode can be used when a switch's particular implementation 
            is not fully recognized by the controller (example: using VxLAN to 
            establish links).

            If the mode is 'switch', 'dpid' kwarg must be specified.

            Returns True if joined, loops if not.
        '''

        self._mode = mode
        if not self.node:
            self._build(**kwargs)

        from api import get_config, add_node
        conf = None
        while conf == None:
            if self.verbose:
                print(' *** Getting configuration', end='\r')
            conf, _ = get_config()
            if conf:
                for param, value in conf.items():
                    if value != None:
                        environ[param] = str(value)
            else:
                sleep(1)
        if self.verbose:
            print()
            print(' *** Done')
        if mode == MODE_CLIENT or mode == MODE_RESOURCE:
            while not self._connected:
                if self.verbose:
                    print(' *** Connecting', end='\r')
                added, code = add_node(self.node)
                if code == HTTP_EXISTS:
                    print(' *** ERROR: Already connected')
                    exit()
                else:
                    if added:
                        self._connected = True
                        if self.verbose:
                            print()
                            print(' *** Done')
                        print(' *** Node added successfully')
                        Thread(target=self._udp_connect).start()
                        Thread(target=self._update_specs).start()

                    else:
                        sleep(1)

        else:
            self._connected = True
            Thread(target=self._update_specs).start()

        return True

    def disconnect(self):
        '''
            Request the withdrawal of the node from the orchestrated topology.

            Returns True if withdrawn properly, False if not.
        '''

        from api import delete_node
        if self.verbose:
            print(' *** Disconnecting')
        self._connected = False
        if self._mode != MODE_SWITCH:
            if delete_node(self.node)[0]:
                if self.verbose:
                    print(' *** Done')
                    print(' *** Node deleted successfully')
                return True
            else:
                if self.verbose:
                    print(' *** Node not deleted')
                return False

    def _get_id(self):
        return ':'.join(findall('..', '%012x' % getnode()))  # MAC

    def _get_label(self):
        return gethostname()

    def _build(self, **kwargs):
        if self.verbose:
            print(' *** Building node and interfaces')
        if self._mode == MODE_SWITCH:
            try:
                id = int(kwargs['dpid'], 16)
            except (KeyError, ValueError):
                print(' *** ERROR in manager._build: '
                      'dpid kwarg invalid or missing.')
                exit()
            type = NodeType(NodeType.SWITCH)
            label = ''
        else:
            id = kwargs.get('id', None)
            if not id:
                id = self._get_id()
            label = kwargs.get('label', None)
            if not label:
                label = self._get_label()
            type = NodeType(NodeType.SERVER)
        self.node = Node(id, True, type, label)
        for name, snics in net_if_addrs().items():
            if name != 'lo':
                interface = Interface(name)
                for snic in snics:
                    if snic.family == AF_INET:
                        interface.ipv4 = snic.address
                    if snic.family == AF_PACKET:
                        interface.mac = snic.address
                self.node.interfaces[name] = interface
        if self.verbose:
            print(' *** Done')

    def _udp_connect(self):
        from common import SERVER_IP
        try:
            UDP_PORT = int(getenv('ORCHESTRATOR_UDP_PORT', None))
        except:
            print(' *** WARNING in manager._udp_connect: '
                  'ORCHESTRATOR:UDP_PORT parameter invalid or missing from '
                  'received configuration. '
                  'Defaulting to 7070.')
            UDP_PORT = 7070
        try:
            UDP_TIMEOUT = float(getenv('ORCHESTRATOR_UDP_TIMEOUT', None))
        except:
            print(' *** WARNING in manager._udp_connect: '
                  'ORCHESTRATOR:UDP_TIMEOUT parameter invalid or missing from '
                  'received configuration. '
                  'Defaulting to 1s.')
            UDP_TIMEOUT = 1
        period = UDP_TIMEOUT / 2
        udp_client = socket(family=AF_INET, type=SOCK_DGRAM)
        while self._connected:
            udp_client.sendto(str(self.node.id).encode(),
                              (SERVER_IP, UDP_PORT))
            sleep(period)
        udp_client.close()

    def _update_specs(self):
        from common import MONITOR
        global MONITOR_PERIOD
        try:
            MONITOR_PERIOD = float(getenv('MONITOR_PERIOD', None))
        except:
            print(' *** WARNING in manager._update_specs: '
                  'MONITOR_PERIOD parameter invalid or missing from received '
                  'configuration. '
                  'Defaulting to 1s.')
            MONITOR_PERIOD = 1
        MONITOR.set_monitor_period(MONITOR_PERIOD)
        MONITOR.start()
        measures = MONITOR.measures

        from simulator import get_resources
        from api import add_node, update_node_specs

        while self._connected:
            sleep(MONITOR_PERIOD)
            # resources are gotten from simulator
            cpu, ram, disk, bw_up, bw_down = get_resources(True)
            if self._mode == MODE_RESOURCE:
                self.node.set_cpu(cpu)
                self.node.set_ram(ram)
                self.node.set_disk(disk)
            for iface in list(self.node.interfaces.values()):
                iface.set_bandwidth_up(bw_up)
                iface.set_bandwidth_down(bw_down)
                # other stats are gotten from monitor
                iface.set_tx_packets(
                    measures.get(iface.name, {}).get('tx_packets', 0))
                iface.set_rx_packets(
                    measures.get(iface.name, {}).get('rx_packets', 0))

            if update_node_specs(self.node)[0]:
                if self.verbose:
                    if self._mode == MODE_RESOURCE:
                        print(' *** Node specs are being sent'.ljust(40),
                              end='\r')
                    else:
                        print(' *** Network specs are being sent'.ljust(40),
                              end='\r')
            else:
                if self.verbose:
                    print(' *** Specs are not being sent'.ljust(40), end='\r')

                # if connection to controller was lost but is back
                # re-add node in case it was deleted
                if self._mode != MODE_SWITCH:
                    add_node(self.node)
