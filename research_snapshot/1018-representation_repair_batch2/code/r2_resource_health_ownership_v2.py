"""Original liveness checks scoped to nodes still leased to this experiment."""
from r2_common import *
import r2_resource_watchdog as original

base_read=original.read


def scoped_read(path):
    data=base_read(path)
    if Path(path)==ROOT/'resources/CLOUD_LATEST.json':
        active={n['name'] for n in base_read(ROOT/'resources/NODES.json')['nodes'] if n.get('active_for_batch2',True)}
        return dict(data,nodes=[n for n in data['nodes'] if n['name'] in active])
    return data


if __name__=='__main__':
    original.read=scoped_read;original.main()
