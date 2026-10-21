"""Describe all actual denoising paths without selecting outcomes or fitting on validation."""
from common import *
import argparse
from collections import defaultdict
import csv
import numpy as np


def run(args):
    from paired_acceptance import load_records
    rows=load_records(args.run,'formal');paired=defaultdict(dict)
    for r in rows:paired[(r['token'],r['noise_group'],r['start_t'])][r['source']]=r
    assert len(paired)==22880
    output=ROOT/'analysis'/args.output;output.mkdir(parents=True,exist_ok=True)
    assert not (output/'COMPLETE.json').exists()
    groups={};scalars=[]
    for index,(key,pair) in enumerate(sorted(paired.items()),1):
        a,b=pair['baseline_failure'],pair['GT'];assert a['array_path']==b['array_path']
        with np.load(a['array_path'],allow_pickle=False) as data:
            h=data['representations'].astype(np.float64);z=data['dit_output'].astype(np.float64)
            # Statistics per actually executed step, stage and action token.
            difference=np.sum((h[1]-h[0])**2,axis=-1)
            magnitude=np.sum((h[1]**2+h[0]**2)/2,axis=-1)
            output_diff=np.sum((z[1]-z[0])**2,axis=-1)
            output_mag=np.sum((z[1]**2+z[0]**2)/2,axis=-1)
            latent=data['latents'].astype(np.float64)
            latent_diff=np.sqrt(np.mean((latent[1]-latent[0])**2,axis=(1,2)))
            final=data['final_trajectories'].astype(np.float64)
            final_ade=float(np.linalg.norm(final[1,:,:2]-final[0,:,:2],axis=1).mean())
            times=data['timesteps'].tolist()
        groups_to_update=[(a['start_t'],a['noise_group'],a['subset'],'all'),
                          (a['start_t'],a['noise_group'],a['subset'],a['primary_mode'])]
        for group in groups_to_update:
            if group not in groups:
                groups[group]=dict(n=0,difference=np.zeros_like(difference),magnitude=np.zeros_like(magnitude),
                    output_diff=np.zeros_like(output_diff),output_mag=np.zeros_like(output_mag),
                    latent_diff=np.zeros_like(latent_diff),times=times,final_ade=0.,score_gap_abs=0.)
            stat=groups[group];stat['n']+=1
            for name,value in [('difference',difference),('magnitude',magnitude),('output_diff',output_diff),('output_mag',output_mag),('latent_diff',latent_diff)]:stat[name]+=value
            stat['final_ade']+=final_ade;stat['score_gap_abs']+=abs(b['score']['score']-a['score']['score'])*100
        scalars.append(dict(token=a['token'],session=a['session'],subset=a['subset'],primary_mode=a['primary_mode'],
            start_t=a['start_t'],noise_group=a['noise_group'],baseline_initialized_pdms_100=100*a['score']['score'],
            gt_initialized_pdms_100=100*b['score']['score'],final_branch_ade_m=final_ade,
            original_gt_pdms_100=100*a['original_gt_score']['score'],
            high_fail_pair={a['quality'],b['quality']}=={'failure','high_quality'}))
        if index%512==0:
            atomic(output/'STATUS.json',dict(status='TEMPORAL',completed=index,total=len(paired),time=stamp()))
            print(json.dumps(dict(completed=index,total=len(paired))),flush=True)
    results=[]
    for key,stat in sorted(groups.items()):
        results.append(dict(start_t=key[0],noise_group=key[1],subset=key[2],mode=key[3],pairs=stat['n'],executed_timesteps=stat['times'],
            relative_representation_difference=np.sqrt(stat['difference']/np.maximum(stat['magnitude'],1e-30)).tolist(),
            relative_dit_output_difference=np.sqrt(stat['output_diff']/np.maximum(stat['output_mag'],1e-30)).tolist(),
            latent_difference_rms=(stat['latent_diff']/stat['n']).tolist(),
            final_branch_ade_m=stat['final_ade']/stat['n'],final_pdms_abs_gap=stat['score_gap_abs']/stat['n']))
    atomic(output/'temporal_summary.json',results)
    with (output/'paired_final_quality.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(scalars[0]));writer.writeheader();writer.writerows(scalars)
    atomic(output/'COMPLETE.json',dict(status='COMPLETE',time=stamp(),source_run=args.run,pairs=len(paired),
        summaries=len(results),all_outcomes_retained=True,quality_gate='final denoising and rescore only',test_cache_access=False))
    print(json.dumps(dict(status='COMPLETE',pairs=len(paired),summaries=len(results))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();setup(f'analysis/{a.output}');compatibility();run(a)
