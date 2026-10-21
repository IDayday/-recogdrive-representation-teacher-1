"""Actual card/model/trajectory/score smoke for the independent batch-two runtime."""
from r2_common import *
import argparse
import traceback


def main(args):
    setup(f'smoke/{args.node}/{args.device}')
    compatibility()
    import torch
    import numpy as np
    from vlm_intervene_v4 import Engine
    from vlm_core import raw_features
    from worker import load_features
    from repair_engine import baseline_row
    from repair_score import score_group
    assert torch.cuda.is_available() and torch.cuda.device_count() == 1
    output = RUN / 'smoke' / args.node / f'device{args.device:02d}.json'
    atomic(output.with_suffix('.status.json'), {'status': 'LOADING', 'time': stamp(), 'rank': args.rank})
    began = time.monotonic()
    engine = Engine()
    checks = []
    anchors = read(ROOT / 'manifests/anchors.json')[:2 if args.device == 0 else 1]
    with torch.no_grad():
        for row in anchors:
            raw = raw_features(row)
            cached, _, _ = load_features(row, engine.cfg)
            hidden = engine.forward_native(raw)
            assert torch.equal(hidden[0].cpu(), cached['last_hidden_state']), 'Native/cache hidden mismatch'
            reference = baseline_row(row)
            native = engine.trajectory(raw, hidden, seed(row['token']))
            assert np.array_equal(native.cpu().numpy(), reference['trajectory']), 'Base trajectory mismatch'
            names = list(engine.prefix)
            selected = names if args.device == 0 else list(dict.fromkeys(
                ['interface_pre', 'interface_post', names[args.rank % len(names)]]))
            for block in selected:
                restored, interface = engine.suffix(block, engine.prefix[block])
                assert torch.equal(restored, hidden), ('Identity suffix mismatch', block)
                if interface is not None:
                    assert torch.equal(engine.trajectory(raw, restored, seed(row['token']), interface), native)
            h = engine.prefix['interface_post']
            d = h.shape[-1]
            basis = torch.zeros((d, 1), device='cuda'); basis[0, 0] = 1
            fit = dict(basis=basis, center=torch.zeros(d, device='cuda'),
                       mh=h.float().norm().reshape(1) / 100, mf=torch.zeros(1, device='cuda'))
            arm = dict(block='interface_post', group='valid_mean', method='mean', alpha=0., cap=.005)
            identity, _ = engine.edited(arm, fit)
            assert torch.equal(identity, h)
            altered, stat = engine.edited(dict(arm, alpha=1.), fit)
            assert float(stat[0]) > 0 and float(stat[0] / stat[1]) <= .005 + 1e-6
            candidate = engine.trajectory(raw, hidden, seed(row['token']), altered)
            scored = score_group(dict(metric_cache=row['metric_cache'], metric_sha256=reference['metric_sha256'],
                                 scoring=engine.cfg['scoring'], records=[
                                     dict(arm='baseline', trajectory=native.cpu().numpy().tolist()),
                                     dict(arm='engineering_nonzero', trajectory=candidate.cpu().numpy().tolist())]))
            assert scored[0]['score'] == reference['score']
            checks.append(dict(token=row['token'], zero_sites=selected, native_hidden_exact=True,
                               trajectory_exact=True, score_exact=True, actual_nonzero_norm=float(stat[0]),
                               relative_edit=float(stat[0] / stat[1]), engineering_scores=scored))
    engine.verify_engine()
    atomic(output, dict(status='PASS', time=stamp(), node=args.node, device=args.device, rank=args.rank,
           seconds=time.monotonic()-began, checks=checks, gpu=torch.cuda.get_device_name(0),
           memory_bytes=torch.cuda.get_device_properties(0).total_memory, planner=engine.planner_runtime,
           first_batch_code_readonly=True, engineering_perturbation_not_a_scientific_candidate=True))
    print('GPU_SMOKE_PASS', args.node, args.device, time.monotonic()-began, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--node', required=True)
    p.add_argument('--device', type=int, required=True); p.add_argument('--rank', type=int, required=True)
    args = p.parse_args()
    try: main(args)
    except BaseException as error:
        atomic(RUN / 'failures' / f'smoke_{args.node}_{args.device}.json',
               dict(status='FAILED', time=stamp(), error=repr(error), traceback=traceback.format_exc()))
        raise
