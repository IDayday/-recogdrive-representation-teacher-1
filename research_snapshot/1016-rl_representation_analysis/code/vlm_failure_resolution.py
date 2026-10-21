"""Acknowledge only an exact archived failure with a fresh replacement heartbeat."""
from common import *


def acknowledged(path, resume):
    ledger=resume/'RESOLVED_FAILURES.json'
    if not ledger.exists():return False
    for r in read(ledger)['records']:
        if (ROOT/r['marker']).resolve()!=path.resolve():continue
        actual=read(path)
        if not all(actual.get(k)==v for k,v in r['signature'].items()):return False
        if not (ROOT/r['signature']['original_log']).exists():return False
        if sha(ROOT/r['signature']['original_log'])!=r['old_log_sha256']:return False
        if not (ROOT/r['status_path']).exists():return False
        s=read(ROOT/r['status_path'])
        age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(s['time'])).total_seconds()
        if s['status'] not in ['RUNNING','COMPLETE'] or age>120:return False
        if s['pid']!=r['replacement_pid']:return False
        return True
    return False
