"""Include late actual failure-only ungated outputs in the complete operator library."""
from common import *
from vlm_core import VOUT
DEST=VOUT/'qda_neighbor_repair'
from vlm_all_oracle import sources as earlier_sources


def sources():
    yield from earlier_sources()
    if (DEST/'ungated/ACCEPTANCE.json').exists():
        r=read(DEST/'ungated/ACCEPTANCE.json');assert sha(ROOT/r['score_path'])==r['scores_sha256']
        yield dict(id='vlm_ungated_qneighbor__failure_gated',path=ROOT/r['score_path'],rows=read(DEST/'ungated/rows.json'),
            arms=read(DEST/'ungated/arms.json'),seeds=r['seeds'],scope=r['scope'])


if __name__=='__main__':
    import vlm_oracle_all,vlm_oracle_policy_groups
    setup('vlm_repair/all_oracle')
    original_family=vlm_oracle_policy_groups.family
    def family(source,arm):
        return 'upstream_representation' if source['id'].startswith('vlm_ungated_') else original_family(source,arm)
    vlm_oracle_all.sources=sources;vlm_oracle_policy_groups.sources=sources;vlm_oracle_policy_groups.family=family
    vlm_oracle_all.main();vlm_oracle_policy_groups.main()
