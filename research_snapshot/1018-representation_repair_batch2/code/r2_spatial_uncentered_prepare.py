"""Matched uncentered counterparts at each frozen centered proposal location."""
from r2_common import *


def run(task):
    parent=ROOT/'config/SPATIAL_DISCOVERY_WAVE1.json';d=read(parent);lookup={}
    for path in [ROOT/'config/REPRESENTATION_LOCATION_PROTOCOL.json',ROOT/'config/FOLD_LOCATION_PROTOCOL.json']+sorted((ROOT/'config/family_locations').glob('*.json')):
        for t in read(path)['tasks']:
            if not t['centered']:lookup[(t['responsibility_meta'],t['expert'],t['cell']['cell'])]=t
    entries=[]
    for entry in d['entries']:
        original=entry['task'];task=lookup[(original['responsibility_meta'],original['expert'],original['cell']['cell'])]
        assert task['heldout_fold']==entry['heldout_fold']
        entries.append(dict(entry,id=task['id'],task=task,paired_centered_id=entry['id'],
            response_stage='spatial_discovery_global_uncentered_v1' if entry['global_repr'] else 'fold_and_outcome_probes_v1'))
    path=ROOT/'config/SPATIAL_DISCOVERY_WAVE1_UNCENTERED.json';atomic(path,dict(d,time=stamp(),entries=entries,parent_manifest=str(parent.relative_to(ROOT)),parent_sha256=sha(parent),
        location_rule='Same exact expert/cell/fold as centered proposal; uncentered own spaces. Complete broad searches stay intact.',centered=False))
    return dict(path=str(path.relative_to(ROOT)),entries=len(entries))
