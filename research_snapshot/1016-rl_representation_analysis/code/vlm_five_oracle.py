"""Include late actual failure-only ungated outputs in the complete operator library."""
from common import *
from vlm_core import VOUT
DEST=VOUT/'observation_qda_gate'
from vlm_four_oracle import sources as earlier_sources


def sources():
    for item in earlier_sources():
        if item['id'].endswith('final_test_obs_qda_parent_union'):item['scope']='Conditional union of risk-positive and diagnostic Base-failure cases; not full-test unconditional parent performance.'
        elif item['id'].endswith('final_test_obs_qda_gate'):item['scope']='Deployable observation-only QDA gate; all risk-positive false-positive harms actually inferred, all remaining outputs are exact Base by policy definition.'
        yield item
    if (DEST/'ungated/ACCEPTANCE.json').exists():
        r=read(DEST/'ungated/ACCEPTANCE.json');assert sha(ROOT/r['score_path'])==r['scores_sha256']
        yield dict(id='vlm_ungated_observation_qda__failure_gated',path=ROOT/r['score_path'],rows=read(DEST/'ungated/rows.json'),
            arms=read(DEST/'ungated/arms.json'),seeds=r['seeds'],scope=r['scope'])


if __name__=='__main__':
    import vlm_oracle_all,vlm_oracle_policy_groups
    setup('vlm_repair/all_oracle')
    original_family=vlm_oracle_policy_groups.family
    def family(source,arm):
        return 'upstream_representation' if source['id'].startswith('vlm_ungated_') else original_family(source,arm)
    vlm_oracle_all.sources=sources;vlm_oracle_policy_groups.sources=sources;vlm_oracle_policy_groups.family=family
    vlm_oracle_all.main();vlm_oracle_policy_groups.main()
