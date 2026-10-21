"""Include explicitly external-failure-gated VLM diagnostics without inventing outputs."""
from common import *
from vlm_core import VOUT
from vlm_semantic import SEM
from vlm_oracle_all import sources as original_sources

def sources():
    for item in original_sources():
        if 'ungated_failures_s' in item['id']:item['scope']='Seed-specific conditional Base-failure subset only; raw means are not full-test population performance.'
        yield item
    for study,dest in [('primary',VOUT/'final/ungated'),('semantic',SEM/'repair/ungated')]:
        if not (dest/'ACCEPTANCE.json').exists():continue
        r=read(dest/'ACCEPTANCE.json');assert sha(ROOT/r['score_path'])==r['scores_sha256']
        yield dict(id='vlm_ungated_'+study+'__failure_gated',path=ROOT/r['score_path'],rows=read(dest/'rows.json'),arms=read(dest/'arms.json'),seeds=r['seeds'],scope=r['scope'])

if __name__=='__main__':
    import vlm_oracle_all,vlm_oracle_policy_groups
    setup('vlm_repair/oracle_with_ungated')
    original_family=vlm_oracle_policy_groups.family
    def family(source,arm):
        return 'upstream_representation' if source['id'].startswith('vlm_ungated_') else original_family(source,arm)
    vlm_oracle_all.sources=sources;vlm_oracle_policy_groups.sources=sources
    vlm_oracle_policy_groups.family=family
    vlm_oracle_all.main();vlm_oracle_policy_groups.main()
