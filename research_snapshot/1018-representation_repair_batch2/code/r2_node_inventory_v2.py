"""Read-only task-owned process inventory for an explicitly named live node."""
from r2_common import *
import argparse


def main(a):
    import psutil
    assert socket.gethostname().startswith(a.job+'-')
    records = []
    for p in psutil.process_iter(['pid','ppid','create_time','cmdline','cwd','status']):
        try:
            d = p.info; args = d['cmdline'] or []
            # Only our two named task roots, never unrelated credential args.
            scripts=[]
            for token in args:
                if not token.endswith(('.py','.sh')):continue
                candidate=Path(token)
                if not candidate.is_absolute():candidate=Path(d['cwd'] or '/')/candidate
                resolved=candidate.resolve()
                if resolved.is_relative_to(ROOT) or resolved.is_relative_to(OLD):scripts.append(str(resolved))
            if not scripts: continue
            records.append(dict(d, matching_scripts=scripts,
                children=[c.pid for c in p.children(recursive=True)],
                cpu_seconds=sum(p.cpu_times()[:2]), rss_bytes=p.memory_info().rss))
        except (psutil.NoSuchProcess, psutil.AccessDenied): continue
    atomic(ROOT/a.output, dict(time=stamp(), job=a.job, hostname=socket.gethostname(),
        processes=records, no_process_or_resource_mutation=True))
    print(json.dumps(dict(status='READONLY_INVENTORY_SAVED', processes=len(records), output=a.output)))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--job', required=True); p.add_argument('--output', required=True)
    main(p.parse_args())
