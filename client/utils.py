from socket import socket, AF_INET, SOCK_DGRAM


def get_ip():
    '''
        Returns the "primary" IP of the node (the one with a default route).
    '''

    with socket(AF_INET, SOCK_DGRAM) as s:
        s.settimeout(0)
        try:
            # doesn't even have to be reachable
            s.connect(('10.254.254.254', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP
