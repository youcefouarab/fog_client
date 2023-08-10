'''
    CLI adapted from the old netapp_sim application.
'''


from threading import Thread

from consts import MODE_RESOURCE


def _list_cos(cos_names: dict):
    print()
    for id, name in cos_names.items():
        print(' ', id, '-', name, end=' ')
        if id == 1:
            print('(default)', end='')
        print()
    print()


def _send_request(send_request, cos_names, cos_id: int, data: bytes):
    print(send_request(cos_id=cos_id, data=data))
    _list_cos(cos_names)


def netapp_cli(mode: str, send_request, cos_names: dict):
    print('\nChoose a Class of Service and click ENTER to send a request')
    if mode == MODE_RESOURCE:
        print('Or wait to receive requests')
    _list_cos(cos_names)
    while True:
        cos_id = input()
        if cos_id == '':
            cos_id = 1
        try:
            cos_id = int(cos_id)
        except:
            print('Invalid CoS ID')
            _list_cos(cos_names)
        else:
            if cos_id not in cos_names:
                print('This CoS doesn\'t exist')
                _list_cos(cos_names)
            else:
                Thread(target=_send_request,
                       args=(send_request, cos_names,
                             cos_id, b'data + program'), daemon=True).start()
