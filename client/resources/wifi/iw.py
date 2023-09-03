from subprocess import run
from psutil import net_if_stats


iw_dict = {}


def launch_iw():
    global iw_dict
    for iface in net_if_stats():
        if iface != 'lo':
            data = run('iw dev %s station dump' % iface,
                       capture_output=True, shell=True, text=True)
            if data.stdout:
                lines = data.stdout.split('\n')
                first_line = lines.pop(0)
                if first_line.startswith('Station'):
                    iw_dict[iface] = {}
                    for line in lines:
                        if line:
                            key, val = line.split(':')
                            key = key.replace('\t', '').strip(' ')
                            val = val.replace('\t', '').strip(' ')
                            iw_dict[iface][key] = val


# for testing
if __name__ == '__main__':
    launch_iw()
    from pprint import pprint
    pprint(iw_dict)
