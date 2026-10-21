"""Joint locked-policy inference across the three prespecified upstream batches."""
from common import *
import copy
from vlm_core import VOUT
from vlm_semantic import SEM
from vlm_late_qualification import DEST
from vlm_final_statistics import comparisons
from repair_queue_v2 import atomic_unique as atomic


def main():
    setup('vlm_repair/all_statistics')
    assert (VOUT/'FINAL_ANALYSES_REVIEW_READY.json').exists()
    old_path=ROOT/read(VOUT/'ALL_STATISTICS_LATEST.json')['path']
    previous=read(old_path);summaries=copy.deepcopy(previous['studies'])
    for study in summaries:
        stage={'semantic_correction':'final_test_semantic','primary':'final_test','late_token':'final_test_late'}[study['study']]
        assert study['score_sha256']==sha(VOUT/'analysis'/stage/'scores.npy')
    neighbor=VOUT/'qda_neighbor_repair';neighbor_done=(neighbor/'SCIENTIFIC_ACCEPTANCE.json').exists()
    assert neighbor_done or (neighbor/'NO_COMPETITIVE_CANDIDATES.json').exists()
    if neighbor_done:
        result=comparisons(VOUT/'analysis/final_test_qneighbor',read(neighbor/'TEST_LOCK.json'))
        result['study']='qda_neighbors'
        for contrast in result['contrasts']:contrast['study']='qda_neighbors'
        summaries.append(result)
    records=[c for study in summaries for c in study['contrasts']]
    for family in {c['family'] for c in records}:
        group=sorted([c for c in records if c['family']==family],key=lambda c:c['p_one_sided']);highest=0.
        for i,c in enumerate(group):
            highest=max(highest,min(1.,c['p_one_sided']*(len(group)-i)));c['p_holm']=highest
    destination=VOUT/'statistics_four'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')
    result=dict(status='PASS',time=stamp(),studies=summaries,joint_all_prespecified_batches=True,
        semantic_complete=bool((SEM/'repair/SCIENTIFIC_ACCEPTANCE.json').exists()),late_complete=previous['late_complete'],qda_neighbors_complete=neighbor_done,
        late_no_competitive=(DEST/'NO_COMPETITIVE_CANDIDATES.json').exists(),
        original_statistics_path=str(old_path.relative_to(ROOT)),original_statistics_sha256=sha(old_path),
        original_math_unchanged=True,code_sha256=sha(Path(__file__)),
        correction='Holm jointly across all unique locked role contrasts in each prespecified hypothesis family.')
    atomic(destination/'FINAL_STATISTICS.json',result)
    atomic(VOUT/'ALL_FOUR_STATISTICS_LATEST.json',dict(path=str((destination/'FINAL_STATISTICS.json').relative_to(ROOT)),sha256=sha(destination/'FINAL_STATISTICS.json')))
    print('ALL_FOUR_BATCHES_STATISTICS_PASS',len(summaries),flush=True)


if __name__=='__main__':main()
