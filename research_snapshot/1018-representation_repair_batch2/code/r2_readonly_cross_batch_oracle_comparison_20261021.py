"""Posthoc reduction of existing frozen test scores; no inference or selection.

Writes only a new diagnostic JSON. Never changes the frozen report or protocols.
The 30-expert union is not a single K=30 trained system or a matched-budget claim.
"""
from pathlib import Path
import ast
import datetime as dt
import hashlib
import json
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / "1016-rl_representation_analysis"


def read(path):
    return json.loads(path.read_text())


def fingerprint(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for value in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(value)
    return h.hexdigest()


def literal_assignment(path, name):
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError((path, name))


def main():
    assessment_path = ROOT / "analysis/frozen_natural_assessment/batch2_test_v1_assessment/SUMMARY.json"
    assessment = read(assessment_path)
    matrix_path = ROOT / assessment["matrix"]
    assert fingerprint(matrix_path) == assessment["matrix_sha256"]
    with np.load(matrix_path, allow_pickle=False) as z:
        scores, arms, seeds, panel = z["scores"], z["arms"].tolist(), z["seeds"].tolist(), z["panel"]
    assert seeds == [0, 1, 2, 3, 4]
    rows = read(ROOT / assessment["rows"])
    old_rows = read(OLD / "vlm_repair_v1/analysis/final_test/rows.json")
    assert [rows[int(i)]["token"] for i in panel] == [r["token"] for r in old_rows]
    base = scores[:, arms.index("baseline")]
    old_fields = ["score"] + literal_assignment(OLD / "code/common.py", "COMPONENTS")
    new_fields = literal_assignment(ROOT / "code/r2_point_response.py", "FIELDS")
    assert set(old_fields) == set(new_fields) and new_fields[0] == "score"
    old_to_new = [old_fields.index(f) for f in new_fields]
    n, draws, fields = base.shape
    assert (n, draws, fields) == (12146, 5, 7)
    ii, jj = np.arange(n)[:, None], np.arange(draws)[None, :]

    # Reproduce all nine already accepted own-K diagnostics before any union.
    pack = read(ROOT / "provenance/final_confirmation/PACK.json")
    for entry in pack["policies"]:
        if entry["kind"] == "Base":
            continue
        policy = read(ROOT / entry["policy"])
        parts = policy["configuration"]["model"]["parts"] if entry["kind"] in ("joint", "finite") else policy["parts"]
        candidates = scores[:, [arms.index("baseline")] + [arms.index("candidate_" + p["id"]) for p in parts]]
        chosen = candidates[ii, candidates[:, :, :, 0].argmax(1), jj]
        actual = float(((chosen[:, :, 0] - base[:, :, 0]) * 100).mean())
        assert abs(actual - assessment["privileged_diagnostics"][entry["id"]]["actual_candidate_oracle"]["mean_PDMS_gain"]) < 1e-12

    old_path = OLD / "vlm_repair_v1/oracle_policy_groups/20261017T172416/SUMMARY.json"
    old_pool = next(p for p in read(old_path)["compatible_pools"] if p["cases"] == n and p["seeds"] == seeds)
    old_panels = {}
    sources = [{"path": str(matrix_path), "sha256": assessment["matrix_sha256"]}]

    def old_candidates(group):
        values = [base]
        for method in old_pool["groups"][group]["methods"]:
            name = method["panel"]
            if name not in old_panels:
                meta = read(OLD / "vlm_repair_v1/oracle_all/panels" / (name + ".json"))
                path = OLD / meta["source_path"]
                assert fingerprint(path) == meta["scores_sha256"]
                array = np.load(path, mmap_mode="r", allow_pickle=False)
                assert np.array_equal(array[:, :, 0, :][:, :, old_to_new].transpose(1, 0, 2), base)
                old_panels[name] = (meta, array)
                sources.append({"path": str(path), "sha256": meta["scores_sha256"]})
            meta, array = old_panels[name]
            ids = [v["arm"]["id"] for v in meta["methods"]]
            values.append(np.asarray(array[:, :, ids.index(method["id"]) + 1, :])[:, :, old_to_new].transpose(1, 0, 2))
        return np.stack(values, 1)

    failure = base[:, :, 0] < .7

    def summarize(candidates):
        picked = candidates[ii, candidates[:, :, :, 0].argmax(1), jj]
        delta = (picked[:, :, 0] - base[:, :, 0]) * 100
        fixed = candidates[np.arange(n), candidates[:, :, 0, 0].argmax(1)]
        fixed_all = candidates[np.arange(n), candidates[:, :, :, 0].mean(2).argmax(1)]
        return {
            "candidate_entries_excluding_Base": int(candidates.shape[1] - 1),
            "all_case_Oracle_gain": float(delta.mean()),
            "all_case_Oracle_gain_per_noise": delta.mean(0).tolist(),
            "failure_only_Oracle_gain": float(np.where(failure, delta, 0).mean()),
            "failure_outputs_repaired_above90": int((failure & (picked[:, :, 0] > .9)).sum()),
            "S0_fixed_candidate_mean_gain": float(((fixed[:, :, 0] - base[:, :, 0]) * 100).mean()),
            "all_noise_privileged_scene_fixed_mean_gain": float(((fixed_all[:, :, 0] - base[:, :, 0]) * 100).mean()),
        }, picked

    raw_ids = [arms.index("baseline")] + [j for j, name in enumerate(arms) if name.startswith("candidate_")]
    assert len(raw_ids) == 31
    new_bank = scores[:, raw_ids]
    upstream_bank = old_candidates("upstream_representation")
    all_old_bank = old_candidates("all_representation")
    results = {}
    for label, bank in [("batch1_upstream_11", upstream_bank), ("batch1_all_representation_21", all_old_bank), ("batch2_confirmed_raw_30_union", new_bank), ("batch1_upstream_plus_batch2_raw", np.concatenate([upstream_bank, new_bank[:, 1:]], 1)), ("batch1_all_representation_plus_batch2_raw", np.concatenate([all_old_bank, new_bank[:, 1:]], 1))]:
        results[label], _ = summarize(bank)
    for group, label in [("upstream_representation", "batch1_upstream_11"), ("all_representation", "batch1_all_representation_21")]:
        expected = old_pool["groups"][group]
        assert abs(results[label]["all_case_Oracle_gain"] - expected["all_case"]["delta_pdms"]) < 1e-12
        assert abs(results[label]["failure_only_Oracle_gain"] - expected["failure_only"]["delta_pdms"]) < 1e-12

    comparisons = {}
    for label in ("upstream", "all_representation"):
        old_label = "batch1_upstream_11" if label == "upstream" else "batch1_all_representation_21"
        combined = results["batch1_" + label + "_plus_batch2_raw"]
        previous = results[old_label]
        comparisons[label] = {"batch2_marginal_all_case_gain_over_batch1": combined["all_case_Oracle_gain"] - previous["all_case_Oracle_gain"], "batch2_marginal_failure_only_gain_over_batch1": combined["failure_only_Oracle_gain"] - previous["failure_only_Oracle_gain"]}

    output = {
        "status": "PASS_READONLY_POSTHOC_EXISTING_SCORE_COMPARISON",
        "time": dt.datetime.now(dt.timezone.utc).isoformat(),
        "new_model_inferences": 0, "new_scores": 0,
        "cases": n, "seeds": seeds,
        "token_order_and_all_seven_Base_fields_exactly_match": True,
        "field_alignment": {"batch1": old_fields, "batch2": new_fields, "batch1_reordering_indices": old_to_new},
        "accepted_ownK_diagnostics_reproduced": 9,
        "original_batch1_group_Oracles_reproduced": 2,
        "results": results, "comparisons": comparisons,
        "scope": "Posthoc descriptive diagnosis on already-scored final-test candidates, not a frozen confirmation endpoint or a selection rule. Only 30 raw experts admitted to final natural confirmation, not all batch2 exploration policies. No matched31Base or matched42Base control. Different candidate pools, budgets and internal gates; no claim of matched causal superiority or of distilled student gains.",
        "sources": sources, "script_sha256": fingerprint(Path(__file__)),
    }
    folder = ROOT / "analysis/posthoc_cross_batch_oracle_20261021"
    folder.mkdir(exist_ok=False)
    (folder / "SUMMARY.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k != "sources"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
