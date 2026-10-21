"""Retire one exact metadata-only EM producer, preserving scientific workers."""
from r2_common import *
import psutil


def main():
    assert socket.gethostname().startswith('dlcrnshl7t4hcmoy-')
    folder=ROOT/'provenance/selected_em1_K3_replication'
    assert not (folder/'METADATA_RETIRED.json').exists()
    live=read(RUN/'control_plane/LIVE.json')
    assert live['node']=='self_0' and live['pid']==102328
    name='feedback_behavior_expert_refits'
    state=live['children'][name]
    assert state['returncode'] is None
    definition=next(x for x in read(ROOT/'config/CONTROL_SCRIPTS_V1.json')['scripts'] if x['id']==name)
    source=ROOT/definition['script']
    assert sha(source)==definition['source_sha256']=='ecf8faee178ff30236d9055fb632db93b3588e5e67f2c3083531e9fc430edd83'
    process=psutil.Process(state['pid'])
    record=dict(pid=process.pid,created=process.create_time(),cmdline=process.cmdline(),uid=process.uids().real)
    assert process.ppid()==live['pid'] and not process.children(recursive=True)
    assert str(source) in record['cmdline'] and record['uid']==os.getuid()
    queues={}
    for stage in ['em_behavior_experts_v1','em_behavior_quick_v1']:
        p=ROOT/'runs'/stage/'tasks.json'
        data=read(p)
        atomic(folder/(stage+'_ORIGINAL_TASKS.json'),data)
        queues[stage]=dict(count=len(data),canonical_digest=digest(data),file_sha256=sha(p))
    atomic(folder/'METADATA_RETIRE_INTENT.json',dict(time=stamp(),process=record,queues=queues,definition=definition))
    assert process.create_time()==record['created'] and process.cmdline()==record['cmdline']
    process.terminate()
    for _ in range(100):
        if not process.is_running() or process.status()==psutil.STATUS_ZOMBIE:break
        time.sleep(.1)
    assert not process.is_running() or process.status()==psutil.STATUS_ZOMBIE
    for stage, before in queues.items():
        data=read(ROOT/'runs'/stage/'tasks.json')
        assert digest(data)==before['canonical_digest'], 'Unreviewed concurrent metadata write'
    atomic(folder/'METADATA_RETIRED.json',dict(status='EXACT_IDLE_METADATA_PRODUCER_RETIRED',
        time=stamp(),process=record,source_sha256=sha(source),queues=queues,
        no_scientific_worker_or_node_or_main_stopped=True))
    print(json.dumps(dict(status='PASS_EXACT_METADATA_ONLY_HANDOFF',pid=record['pid'],queues=queues)),flush=True)


if __name__=='__main__':
    main()
