"""Prepared scene-local execution of formed experts and complete policies.

Raw experts are memoized by executable semantic identity. A selected hard branch
keeps its actual trajectory/interface pair. A soft joint policy executes the
original joint network intervention. No outcome score enters these policies.
Runtime admission and frozen manifests are required before formal use.
"""
from r3_common import *
from dataclasses import dataclass, replace
from functools import lru_cache


@dataclass
class Branch:
    trajectory: object
    interface: object
    relative_edit: float
    source: str
    diagnostic: dict


@lru_cache(maxsize=128)
def policy_data(path, expected):
    path=Path(path);path=path if path.is_absolute() else BATCH2/path
    assert sha(path)==expected
    result=read(path);assert result['heldout_fold']==-1
    return result


class Scene:
    def __init__(self,engine,features,token,noise_indices=(0,1,2,3,4)):
        import torch
        from r3_runtime import Fits
        assert not torch.is_grad_enabled()
        self.engine=engine;self.features=features;self.token=token;self.seeds=tuple(noise_indices)
        self.hidden=engine.forward_native(features);self.native={};self.states={};self.parts={}
        self.fit1=Fits(BATCH1);self.fit2=Fits(BATCH2);self.observations={};self.contexts={}

    def predict(self,hidden,j,interface=None,trace=False):
        import torch
        from r3_runtime import prediction
        if not trace:return prediction(self.engine,self.features,hidden,j,self.token,interface)
        head=self.engine.agent.action_head;original=head.p_mean_variance;states=[]
        had='p_mean_variance' in head.__dict__;previous=head.__dict__.get('p_mean_variance')
        def traced(x,*args,**kwargs):
            states.append(x.detach().clone());return original(x,*args,**kwargs)
        head.p_mean_variance=traced
        try:result=prediction(self.engine,self.features,hidden,j,self.token,interface)
        finally:
            if had:head.p_mean_variance=previous
            else:delattr(head,'p_mean_variance')
        assert len(states)==5
        self.states[j]=torch.stack(states).squeeze(1)
        return result

    def base(self,j):
        if j not in self.native:
            value,interface=self.predict(self.hidden,j,trace=True)
            self.native[j]=Branch(value,interface,0.,'Base',{})
        return self.native[j]

    def part(self,part,j):
        import torch
        from r3_formed_catalog_v2 import part_key
        from r2_library_rollouts import apply,block
        key=digest(part_key(part))
        if key not in self.parts:
            changed,statistics=apply(self.engine,part,self.fit2);site=block(part)
            if torch.equal(changed,self.engine.prefix[site]):
                values={n:self.base(n) for n in self.seeds}
            else:
                condition,post=self.engine.suffix(site,changed);values={}
                for n in self.seeds:
                    trajectory,interface=self.predict(condition,n,post)
                    values[n]=Branch(trajectory,interface,float(statistics['relative_edit']),key,{})
            self.parts[key]=values
        return self.parts[key][j]

    def upstream(self,arm,root,j):
        import torch
        from r3_formed_catalog_v2 import arm_key
        from r3_first42_rollout_v2 import observation_gate
        key=digest(dict(root=str(root),arm=arm_key(arm)))
        if key not in self.parts:
            extra={};actual=arm
            if arm['gate']=='external_observation_qda_hard':
                active,risk=observation_gate(self.engine,root,arm)
                extra=dict(observation_gate_active=active,observation_gate_risk=risk)
                actual=dict(arm,gate='none') if active else None
            if actual is None:values={n:replace(self.base(n),diagnostic=extra) for n in self.seeds}
            else:
                changed,stat=self.engine.edited(actual,self.fit1.get(actual))
                condition,post=self.engine.suffix(actual['block'],changed);relative=float(stat[0]/stat[1].clamp(min=1e-12))
                values={}
                for n in self.seeds:
                    trajectory,interface=self.predict(condition,n,post)
                    values[n]=Branch(trajectory,interface,relative,key,extra)
            self.parts[key]=values
        return self.parts[key][j]

    def complete_policy(self,kind,policy,j):
        import numpy as np
        import torch
        from r2_behavior_router import current_feature,checkpoint,coefficients
        base=self.base(j);native=base.trajectory;states=self.states[j];diagnostic={}
        parts=policy['configuration']['model']['parts'] if kind in ['joint','finite'] else policy['parts']
        if kind=='hard':
            from r2_router_runtime import feature,decide
            x=feature(self.engine,native.cpu().numpy(),states.cpu().numpy(),policy)
            choice,diagnostic=decide(policy,x)
        elif kind=='candidate':
            from r2_router_runtime import transforms
            from r2_router_features import from_engine
            from r2_candidate_selector import inputs,decide
            meta=policy['feature_meta'];key=(meta['path'],meta['sha256'])
            if key not in self.observations:
                self.observations[key]=from_engine(self.engine,transforms(*key)).cpu().numpy()
            actual=torch.stack([self.part(p,j).trajectory for p in parts]).cpu().numpy()
            x=inputs(self.observations[key],native.cpu().numpy(),actual,states.cpu().numpy(),[p['slot'] for p in parts],policy['tier'])
            choice,diagnostic=decide(policy,x)
        elif kind=='token':
            from r2_context_critic import load
            from r2_token_policy_select import choices
            critic=policy['critic'];assert critic['heldout_fold']==-1
            view=critic.get('context_view','post_valid')
            if view not in self.contexts:
                site='interface_pre' if view.startswith('pre') else 'interface_post'
                group='all_mean' if view.endswith('all') else 'valid_mean'
                h=self.engine.prefix[site];mask,valid=self.engine.mask(site,group);assert valid
                self.contexts[view]=h.reshape(-1,h.shape[-1])[mask]
            options=[base]+[self.part(p,j) for p in parts]
            actual=torch.stack([v.trajectory for v in options])
            module=load(critic['checkpoint']['path'],critic['checkpoint']['sha256'])
            predicted=module(self.contexts[view],actual).cpu().numpy()
            choice=int(choices(predicted[None],critic['risk_penalty'],critic['threshold'])[0])
            # Keep the original branch object, including the actual interface.
            return replace(options[choice],diagnostic=dict(choice=choice,context_view=view,predicted=predicted.tolist()))
        elif kind in ['finite','joint']:
            setting=policy['configuration'];model=setting['model'];assert model['heldout_fold']==-1
            module=checkpoint(setting['checkpoint']['path'],setting['checkpoint']['sha256'],model['input_dimension'],len(parts))
            logits,amount=module(current_feature(self.engine,native,states,-1,model['tier']))
            if kind=='finite':
                assert model['tier'] in ['observation','trajectory'] and torch.equal(amount,torch.ones_like(amount))
                choice=int(logits.argmax());diagnostic=dict(logits=logits.cpu().tolist(),fixed_strength=1.)
            else:
                from r2_mixed_locations_v3 import forward as mixture
                weights,strength=coefficients(logits,amount,model['kind']);strength=strength*setting.get('multiplier',1.)
                abstain=setting.get('force_Base',False) or bool(weights[0]>=setting.get('identity_threshold',1.01)) or (model['kind']=='hard_continuous' and int(weights.argmax())==0)
                diagnostic=dict(weights=weights.cpu().tolist(),strengths=strength.cpu().tolist(),abstained=abstain)
                if abstain:return replace(base,diagnostic=diagnostic)
                condition,post,stats=mixture(self.engine,parts,weights,strength,self.fit2)
                trajectory,interface=self.predict(condition,j,post)
                relative=float(torch.stack([v[0]/v[1].clamp(min=1e-12) for v in stats]).max()) if stats else 0.
                return Branch(trajectory,interface,relative,'joint_'+digest(setting),diagnostic)
        else:raise ValueError(kind)
        assert 0<=choice<=len(parts)
        actual=base if choice==0 else self.part(parts[choice-1],j)
        return replace(actual,diagnostic=dict(diagnostic,choice=choice))

    def evaluate(self,entry,j):
        assert j in self.seeds
        kind=entry['kind'];definition=entry['definition']
        if kind=='Base':return self.base(j)
        if kind=='batch1_upstream':return self.upstream(definition['arm'],definition['root'],j)
        if kind=='batch1_action_or_postprocess':
            from r3_legacy_runtime_v1 import prediction
            trajectory,interface,stat=prediction(self.engine,definition['arm'],self.features,self.hidden,self.token,j)
            return Branch(trajectory,interface,stat['relative_edit'],entry['id'],stat)
        if kind in ['batch2_learned','batch2_delta','batch2_analytic']:return self.part(definition,j)
        if kind.startswith('batch2_policy_'):
            policy=policy_data(definition['policy_path'],definition['policy_sha256'])
            return self.complete_policy(kind.removeprefix('batch2_policy_'),policy,j)
        raise ValueError(kind)
