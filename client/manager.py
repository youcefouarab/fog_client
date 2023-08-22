from os import environ, getenv
from threading import Thread
from time import sleep
from psutil import net_if_addrs
from socket import socket, AF_INET, AF_PACKET, SOCK_DGRAM, gethostname
from re import findall
from uuid import getnode

from python_ovs_vsctl import (VSCtl, list_cmd_parser, VSCtlCmdExecError,
                              VSCtlCmdParseError)
from model import Node, NodeType, Interface
from consts import MODE_CLIENT, MODE_RESOURCE, MODE_SWITCH, HTTP_EXISTS
from logger import console, file
from utils import SingletonMeta, all_exit


class Manager(metaclass=SingletonMeta):
    '''
        Singleton class for managing multiple aspects of the client component, 
        such as building the Node and Interface models, managing the connection 
        to the orchestrator, and sending node and/or network specs periodically 
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

        from api import get_config, add_node
        conf = None
        _code = [0, 0]
        console.info('Getting configuration')
        while conf == None:
            conf, *code = get_config()
            if conf:
                for param, value in conf.items():
                    if value != None:
                        environ[param] = str(value)
            else:
                file.error(code)
                if _code[0] != code[0] or _code[1] != code[1]:
                    console.error(code)
                    _code = code
                sleep(1)
        console.info('Done')

        if not self.node:
            self._build(**kwargs)

        if mode == MODE_CLIENT or mode == MODE_RESOURCE:
            from resources import MY_IFACE, THRESHOLD
            self.node.main_interface = MY_IFACE
            self.node.threshold = THRESHOLD

            _code = [0, 0]
            console.info('Connecting')
            while not self._connected:
                added, *code = add_node(self.node)
                if code[0] == HTTP_EXISTS:
                    console.error('Already connected')
                    file.error('%s already connected', str(self.node.id))
                    all_exit()
                else:
                    if added:
                        self._connected = True
                        console.info('Done')
                        console.info('Node added successfully')
                        Thread(target=self._udp_connect, daemon=True).start()
                        Thread(target=self._update_specs, daemon=True).start()

                    else:
                        file.error(code)
                        if _code[0] != code[0] or _code[1] != code[1]:
                            console.error(code)
                            _code = code
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
        console.info('Disconnecting')
        self._connected = False
        if self._mode != MODE_SWITCH:
            if self.node:
                deleted, *code = delete_node(self.node)
                if deleted:
                    console.info('Done')
                    console.info('Node deleted successfully')
                else:
                    console.error('Node not deleted %s', str(code))
                    file.error('Node not deleted %s', str(code))
                    return False
            return True

    def _get_id(self):
        return ':'.join(findall('..', '%012x' % getnode()))  # MAC

    def _get_label(self):
        return gethostname()

    def _build(self, **kwargs):
        console.info('Building node and interfaces')
        if self._mode == MODE_SWITCH:
            try:
                id = kwargs['dpid']
                int(id, 16)
            except KeyError:
                console.error('DPID argument missing')
                file.exception('DPID argument missing')
                all_exit()
            except ValueError:
                console.error('DPID argument invalid (must be hexadecimal)')
                file.exception('DPID argument invalid (must be hexadecimal)')
                all_exit()
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

        if self._mode == MODE_SWITCH:
            try:
                # get ports from OVS
                vsctl = VSCtl()
                for record in vsctl.run('list interface',
                                        parser=list_cmd_parser):
                    # get associated "physical" interface
                    name = record.__dict__.get('name', None)
                    if name:
                        self.node.interfaces[name] = Interface(name)
            except (VSCtlCmdExecError, VSCtlCmdParseError) as e:
                console.error('OVS ports not added due to %s',
                              e.__class__.__name__)
                file.exception('OVS ports not added due to %s',
                               e.__class__.__name__)
        for name, snics in net_if_addrs().items():
            if name != 'lo':
                interface = Interface(name)
                for snic in snics:
                    if snic.family == AF_INET:
                        interface.ipv4 = snic.address
                    if snic.family == AF_PACKET:
                        interface.mac = snic.address
                self.node.interfaces[name] = interface
        console.info('Done')

    def _udp_connect(self):
        from common import SERVER_IP
        try:
            UDP_PORT = int(getenv('ORCHESTRATOR_UDP_PORT', None))
        except:
            console.warning('ORCHESTRATOR:UDP_PORT parameter invalid or '
                            'missing from received configuration. '
                            'Defaulting to 7070')
            file.warning('ORCHESTRATOR:UDP_PORT parameter invalid or missing '
                         'from received configuration', exc_info=True)
            UDP_PORT = 7070
        try:
            UDP_TIMEOUT = float(getenv('ORCHESTRATOR_UDP_TIMEOUT', None))
        except:
            console.warning('ORCHESTRATOR:UDP_TIMEOUT parameter invalid or '
                            'missing from received configuration. '
                            'Defaulting to 1s')
            file.warning('ORCHESTRATOR:UDP_TIMEOUT parameter invalid or '
                         'missing from received configuration', exc_info=True)
            UDP_TIMEOUT = 1
        period = UDP_TIMEOUT / 2
        udp_client = socket(family=AF_INET, type=SOCK_DGRAM)
        while self._connected:
            udp_client.sendto(str(self.node.id).encode(),
                              (SERVER_IP, UDP_PORT))
            sleep(period)
        udp_client.close()

    def _update_specs(self):
        from resources import MEASURES, MONITOR_PERIOD, get_resources
        from api import add_node, update_node_specs

        # constant measures
        from resources import CPU, RAM, DISK
        self.node.set_cpu_count(CPU)
        self.node.set_memory_total(RAM)
        self.node.set_disk_total(DISK)

        _code = [0, 0]
        while self._connected:
            sleep(MONITOR_PERIOD)
            # current resources are gotten from simulator
            cpu, ram, disk = get_resources(quiet=True)
            self.node.set_cpu_free(cpu)
            self.node.set_memory_free(ram)
            self.node.set_disk_free(disk)
            # other stats are gotten from monitor
            for name, iface in list(self.node.interfaces.items()):
                IM = MEASURES.get(name, {})
                iface.set_capacity(IM.get('capacity', None))
                iface.set_bandwidth_up(IM.get('bandwidth_up', None))
                iface.set_bandwidth_down(IM.get('bandwidth_down', None))
                iface.set_tx_packets(IM.get('tx_packets', None))
                iface.set_rx_packets(IM.get('rx_packets', None))

            updated, *code = update_node_specs(self.node)
            if updated:
                if _code[0] != code[0] or _code[1] != code[1]:
                    if self._mode == MODE_RESOURCE:
                        console.info('Node specs are being sent')
                    else:
                        console.info('Network specs are being sent')
                    _code = code

            else:
                file.error('Specs are not being sent %s', str(code))
                if _code[0] != code[0] or _code[1] != code[1]:
                    console.error('Specs are not being sent %s', str(code))
                    _code = code

                # if connection to controller was lost but is back
                # re-add node in case it was deleted
                if self._mode != MODE_SWITCH:
                    add_node(self.node)
