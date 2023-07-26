'''
    Main module of the client component. It can be launched through CLI or used 
    programmatically through the connect(...) method. It requests the joining 
    of a node in the orchestrated topology in one of three modes: client, 
    resource, or switch.

    In all modes, the -s/--server option in the CLI is required to specify the 
    server's IP and API port. Verbosity can also be activated using the 
    -v/--verbose option, so a detailed output will be produced on the console.

    Client mode means the node participates in the orchestration but only to 
    request resources; it has no resources of its own to offer.

    Resource mode includes client mode, but the node also offers its resources 
    for use by other clients and resources.

    If the mode is 'client' or 'resource', it is possible to specify a custom 
    node ID and/or label through -i/--id and -l/--label options respectively 
    (this is useful, and sometimes necessary to avoid conflicts, in simulations 
    and/or emulations like Mininet).

    If the mode is 'resource' and simulation is active, it is possible to 
    specify simulated values for CPU, RAM, and disk through the -c/--cpu,
    -r/--ram, and -d/--disk options respectively.

    Switch mode can be used when a switch's particular implementation is not 
    fully recognized by the controller (example: using VxLAN to establish 
    links).

    If the mode is 'switch', --dpid (-d) must be specified.

    If launched through CLI, an interface for test-sending network application 
    hosting requests would also be started, configured according to the 
    settings received from the server upon connection establishment.
'''


from os import environ
from threading import Thread
from argparse import ArgumentParser, ArgumentTypeError
from atexit import register as at_exit
from signal import signal, SIGINT
from sys import exit as sys_exit
from logging import getLogger
from flask import cli

from consts import *
from manager import Manager
from model import Node


# disable flask console messages
getLogger('werkzeug').disabled = True
cli.show_server_banner = lambda *args: None


def valid_server(s):
    try:
        environ['SERVER_IP'], environ['SERVER_API_PORT'] = s.split(':')
    except ValueError:
        raise ArgumentTypeError(
            '--server format must be IP:PORT (e.g. 127.0.0.1:8080)')


def valid_resources(**kwargs):
    environ['IS_RESOURCE'] = 'True'
    environ['HOST_CPU'] = str(kwargs['cpu'])
    environ['HOST_RAM'] = str(kwargs['ram'])
    environ['HOST_DISK'] = str(kwargs['disk'])
    # environ['HOST_INGRESS'] = str(kwargs['ingress'])
    # environ['HOST_EGRESS'] = str(kwargs['egress'])


parser = ArgumentParser()


def _parse_arguments():
    subparsers = parser.add_subparsers(dest='mode')
    # switch mode
    s_parser = subparsers.add_parser(MODE_SWITCH, help='Connect as switch.')
    s_parser.add_argument('-d', '--dpid', metavar='dpid', required=True,
                          help='Bridge datapath ID (in hexadecimal).')
    s_parser.add_argument('-s', '--server', metavar='server', required=True,
                          # type=valid_server,
                          help='Server IP and API port. Format is IP:PORT.')
    s_parser.add_argument('-v', '--verbose', metavar='verbose', default=False,
                          nargs='?', const=True,
                          help='Detailed output on the console.')
    # client mode
    c_parser = subparsers.add_parser(MODE_CLIENT, help='Connect as client.')
    c_parser.add_argument('-s', '--server', metavar='server', required=True,
                          # type=valid_server,
                          help='Server IP and API port. Format is IP:PORT.')
    c_parser.add_argument('-i', '--id', metavar='id', default=None,
                          help='Custom node ID (for simulations).')
    c_parser.add_argument('-l', '--label', metavar='label', default=None,
                          help='Custom node label (for simulations).')
    c_parser.add_argument('-v', '--verbose', metavar='verbose', default=False,
                          nargs='?', const=True,
                          help='Detailed output on the console.')
    # resource mode
    r_parser = subparsers.add_parser(
        MODE_RESOURCE, help='Connect as resource.')
    r_parser.add_argument('-s', '--server', metavar='server', required=True,
                          # type=valid_server,
                          help='Server IP and API port. Format is IP:PORT.')
    r_parser.add_argument('-i', '--id', metavar='id', default=None,
                          help='Custom node ID (for simulations).')
    r_parser.add_argument('-l', '--label', metavar='label', default=None,
                          help='Custom node label (for simulations).')
    r_parser.add_argument('-c', '--cpu', metavar='cpu', default=None,
                          help='Number of simulated CPUs.')
    r_parser.add_argument('-r', '--ram', metavar='ram', default=None,
                          help='Size of simulated RAM (in MB).')
    r_parser.add_argument('-d', '--disk', metavar='disk', default=None,
                          help='Size of simulated disk (in GB).')
    # r_parser.add_argument('-e', '--egress', metavar='egress', default=None,
    #                      help='Size of simulated egress bandwidth (in Mbps).')
    # r_parser.add_argument('-n', '--ingress', metavar='ingress', default=None,
    #                      help='Size of simulated ingress bandwidth (in Mbps).')
    r_parser.add_argument('-v', '--verbose', metavar='verbose', default=False,
                          nargs='?', const=True,
                          help='Detailed output on the console.')
    return parser.parse_args()


def connect(mode: str, server: str, node: Node = None, verbose: bool = False,
            **kwargs):
    '''
        Request the joining of a node in the orchestrated topology in one of 
        three modes: client, resource, or switch.

        Client mode means the node participates in the orchestration but only 
        to request resources; it has no resources of its own to offer.

        Resource mode includes client mode, but the node also offers its 
        resources for use by other clients and resources.

        If the mode is 'client' or 'resource', it is possible to specify a 
        custom node ID and/or label through 'id' and 'label' kwargs 
        respectively (this is useful, and sometimes necessary to avoid 
        conflicts, in simulations and/or emulations like Mininet).

        If the mode is 'resource' and simulation is active, it is possible to 
        specify simulated values for CPU, RAM, and disk through the 'cpu',
        'ram', and 'disk' kwargs respectively.

        Switch mode can be used when a switch's particular implementation is 
        not fully recognized by the controller (example: using VxLAN to 
        establish links).

        If the mode is 'switch', 'dpid' kwarg must be specified.

        By default, the Node object is automatically built from the node's real 
        data, but a custom Node object can be passed as an argument (which can 
        be useful for simulations and/or testing).

        If verbose is True, a detailed output will be produced on the console.

        Returns the Manager object.
    '''

    if mode not in (MODE_CLIENT, MODE_RESOURCE, MODE_SWITCH):
        parser.print_help()
        sys_exit()

    environ['PROTOCOL_VERBOSE'] = str(verbose)

    valid_server(server)
    if mode == MODE_RESOURCE:
        valid_resources(**kwargs)
    mgr = Manager(node, verbose)

    # disconnect at exit
    def _signal_handler(_, __):
        at_exit(mgr.disconnect)
        print()
        sys_exit()
    signal(SIGINT, _signal_handler)

    mgr.connect(mode, **kwargs)
    return mgr


def _list_cos():
    print()
    for id, name in cos_names.items():
        print(' ', id, '-', name, end=' ')
        if id == 1:
            print('(default)', end='')
        print()
    print()


def _send_request(cos_id: int, data: bytes):
    print(send_request(cos_id=cos_id, data=data))
    _list_cos()


def _cli(mode: str):
    print()
    print('Choose a Class of Service and click ENTER to send a request')
    if mode == MODE_RESOURCE:
        print('Or wait to receive requests')
    _list_cos()
    print()
    from simulator import get_resources
    get_resources(_all=True)
    print()
    while True:
        cos_id = input()
        if cos_id == '':
            cos_id = 1
        try:
            cos_id = int(cos_id)
        except:
            print('Invalid CoS ID')
            _list_cos()
        else:
            if cos_id not in cos_names:
                print('This CoS doesn\'t exist')
                _list_cos()
            else:
                Thread(target=_send_request,
                       args=(cos_id, b'data + program')).start()


if __name__ == '__main__':
    args = _parse_arguments()
    mode = args.mode

    if mode == MODE_CLIENT:
        connect(mode, args.server, verbose=args.verbose != False,
                id=args.id, label=args.label)
    elif mode == MODE_RESOURCE:
        connect(mode, args.server, verbose=args.verbose != False,
                id=args.id, label=args.label, cpu=args.cpu, ram=args.ram,
                disk=args.disk)
    elif mode == MODE_SWITCH:
        connect(mode, args.server, verbose=args.verbose != False,
                dpid=args.dpid)
    else:
        parser.print_help()
        sys_exit()

    if mode in (MODE_CLIENT, MODE_RESOURCE):
        from protocol import PROTO_SEND_TO
        if PROTO_SEND_TO in (SEND_TO_BROADCAST, SEND_TO_ORCHESTRATOR):
            # start gui
            from gui import app
            app.logger.disabled = True
            Thread(target=app.run, args=('0.0.0.0',)).start()
            print('\nGUI started at http://' + MY_IP + ':8050')

            # start cli
            from protocol import send_request, cos_names
            _cli(mode)
