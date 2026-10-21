"""Queue completed held token-policy readout diagnostics on spare CPU workers."""
from r2_common import *
from r2_resume_support import append_once


def main():
    known=set()
    stages=['token_critic_held_predictions_v1','additional_token_critic_held_predictions_v1','uniform_critic_held_predictions_v1','context_pre_valid_held_predictions_v1','context_post_all_held_predictions_v1','context_pre_all_held_predictions_v2','large_success_critic_held_v1']
    while True:
        work=[]
        for name in stages:
            base=ROOT/'runs'/name;receipts={p.stem for p in (base/'receipts').glob('*.json')}
            for path in (base/'points').glob('*.json'):
                point=read(path)
                if point.get('mode')!='heldout' or 'policy' not in point:continue
                if not all((point['id']+'_%04d'%i) in receipts for i in range(0,len(point['items']),8)):continue
                policy=read(ROOT/point['policy']);calpoint=Path(policy['source_point']);calstage=str(calpoint.parent.parent)
                spec=dict(policy=point['policy'],held_point=str(path.relative_to(ROOT)),calibration_stage=calstage,held_stage=str(base.relative_to(ROOT)));ident='outcome_readout_'+digest(spec)[:24]
                if ident not in known:work.append(dict(id=ident,handler='code/r2_critic_readout_diagnostic.py',handler_sha256=sha(ROOT/'code/r2_critic_readout_diagnostic.py'),**spec));known.add(ident)
        if work:append_once('cpu',work)
        atomic(ROOT/'analysis/critic_readout_diagnostics/PRODUCER.json',dict(time=stamp(),queued=len(known)));time.sleep(120)


if __name__=='__main__':main()
