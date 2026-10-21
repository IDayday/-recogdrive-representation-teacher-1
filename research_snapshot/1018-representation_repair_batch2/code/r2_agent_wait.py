"""Tool-owned wait: return a DLC monitor event exactly once to the agent."""
from r2_common import *


def main():
    setup('agent_wait')
    path=RUN/'control_plane/logs/attention_monitor.log';cursor_path=ROOT/'runs/attention_monitor/AGENT_CURSOR.json'
    offset=read(cursor_path).get('offset',0) if cursor_path.exists() else 0
    while True:
        if path.exists():
            with path.open() as stream:
                stream.seek(offset);lines=stream.readlines();position=stream.tell()
            if lines:
                atomic(cursor_path,dict(time=stamp(),offset=position))
                for line in lines:
                    if line.strip():print(line.strip(),flush=True)
                return
        time.sleep(60)


if __name__=='__main__':main()
