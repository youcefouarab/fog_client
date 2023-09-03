from subprocess import run


hostapd_dict = {}


def launch_hostapd():
    data = run('hostapd_cli status',
               capture_output=True, shell=True, text=True)
    global hostapd_dict
    for record in data.stdout.split('\n\n'):
        lines = record.split('\n')
        first_line = lines.pop(0)
        if first_line.startswith('Selected interface'):
            iface = first_line.split('\'')[1]
            hostapd_dict[iface] = {}
            for line in lines:
                if line:
                    key, val = line.split('=')
                    hostapd_dict[iface][key] = val


# for testing
if __name__ == '__main__':
    launch_hostapd()
    from pprint import pprint
    pprint(hostapd_dict)
