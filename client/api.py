'''
    General purpose interface for using the REST API of the orchestrator, 
    providing methods that serve as a facade to hide the complexities of the 
    framework- and/or platform-specific API used. Currently supports Ryu API. 
    Methods of this interface should be redefined and/or extended for other 
    frameworks and/or platforms.

    Methods:
    --------
    get_config(): Send GET request to get the configuration of the protocol, 
    the simulation, etc.

    add_node(node): Send POST request to add node to the orchestrated topology.

    delete_node(id): Send DELETE request to delete node from the orchestrated 
    topology.

    update_node_specs(node): Send PUT request to update node specs (including 
    interface specs).
'''


# !!IMPORTANT!!
# This module relies on config that is only present AFTER the connect()
# method is called, so only import after


from os import getenv
from requests import get, post, put, delete, RequestException

from model import Node
from common import SERVER_IP
from consts import HTTP_EXISTS, HTTP_SUCCESS


try:
    API_PORT = int(getenv('SERVER_API_PORT', None))
except:
    print(' *** ERROR in api: Server API port invalid or missing.')
    exit()


# ====================
#     MAIN METHODS
# ====================


def get_config():
    '''
        Send GET request to get the configuration of the protocol, the 
        simulation, etc.
    '''

    return _ryu_get_config()


def add_node(node: Node):
    '''
        Send POST request to add node to the orchestrated topology.

        Returns (state, code), where state is True if added, False if not.
    '''

    return _ryu_add_node(node)


def delete_node(node: Node):
    '''
        Send DELETE request to delete node from the orchestrated topology.

        Returns (state, code), where state is True if deleted, False if not.
    '''

    return _ryu_delete_node(node)


def update_node_specs(node: Node):
    '''
        Send PUT request to update node specs (including interface specs).

        Returns (state, code), where state is True if updated, False if not.
    '''

    return _ryu_update_node_specs(node)


# ===============
#     RYU API
# ===============


RYU_URL = 'http://' + SERVER_IP + ':' + str(API_PORT)
RYU_HEADERS = {'content-type': 'application/json'}


def _ryu_request(method: str, path: str, data: dict = {}):
    url = RYU_URL + path
    method = method.upper()
    try:
        if method == 'GET':
            r = get(url, headers=RYU_HEADERS, json=data)
            code = r.status_code
            return (r.json(), code) if code == HTTP_SUCCESS else (None, code)
        elif method == 'POST':
            r = post(url, headers=RYU_HEADERS, json=data)
        elif method == 'PUT':
            r = put(url, headers=RYU_HEADERS, json=data)
        elif method == 'DELETE':
            r = delete(url, headers=RYU_HEADERS, json=data)
        code = r.status_code
        return ((code == HTTP_SUCCESS or code == HTTP_EXISTS), code)

    except (RequestException, ValueError) as e:
        return None, None


def _ryu_add_node(node: Node):
    return _ryu_request('post', '/node', {
        'id': node.id,
        'state': node.state,
        'type': node.type.value,
        'label': node.label,
        'interfaces': [{
            'name': iface.name,
            'num': iface.num,
            'mac': iface.mac,
            'ipv4': iface.ipv4
        } for iface in list(node.interfaces.values())]
    })


def _ryu_get_config():
    return _ryu_request('get', '/config')


def _ryu_delete_node(node: Node):
    return _ryu_request('delete', '/node/' + str(node.id))


def _ryu_update_node_specs(node: Node):
    return _ryu_request('put', '/node_specs/' + str(node.id), {
        'cpu_count': node.get_cpu(),
        'memory_free': node.get_ram(),
        'disk_free': node.get_disk(),
        'timestamp': node.get_timestamp(),
        'interfaces': [{
            'name': iface.name,
            'capacity': iface.get_capacity(),
            'bandwidth_up': iface.get_bandwidth_up(),
            'bandwidth_down': iface.get_bandwidth_down(),
            'tx_packets': iface.get_tx_packets(),
            'rx_packets': iface.get_rx_packets(),
            'timestamp': iface.get_timestamp()
        } for iface in list(node.interfaces.values())]
    })
