"""Verify the finished private-prior experiment and recompute quality decisions."""
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.private_prior.run import read, environment_check, verify, CASES
from experiments.private_prior.design import spec
from experiments.quantity_heterogeneity.data import verify as verify_cache
from experiments.stl10_transfer.run import digest


def summarize(record):
    diagnostics = record["diagnostic_records"]
    late = [d for d in diagnostics if 161 <= d["round"] <= 200]
    assert len(late) == 40
    rates = [statistics.mean(d["clients"][c]["positive_relation_fraction_T1"] for d in late)
             for c in range(6)]
    metrics = {m["round"]: m["clients"] for m in record["metrics"]}
    assert set(metrics) == set(range(20,201,20))
    healthy = all(c["occupied_clusters"] > 1 and c["largest_cluster_fraction"] < .99
                  for r in [160,180,200] for c in metrics[r])
    early_events = {str(c): [d["round"] for d in diagnostics[:40]
                             if d["clients"][c]["positive_relation_fraction_T1"] >= .95] for c in (0,3)}
    tests = metrics[200]
    return dict(late_rates=rates, small_late=statistics.mean(rates[c] for c in (0,3)),
                healthy=healthy, early_events=early_events,
                final_teacher_rates=[d["positive_relation_fraction_T1"] for d in diagnostics[-1]["clients"]],
                final_aggregate=record["round_records"][-1]["positive_relation_fraction"],
                final_tests=tests,
                final_mean={k: statistics.mean(c[k] for c in tests) for k in ("acc","nmi","ari")},
                final_private_fit=[c["T2"]["private"]["fixed_pseudo_fit"] for c in diagnostics[-1]["clients"]],
                checkpoint_maxima={str(r): max(c["largest_cluster_fraction"] for c in cs) for r,cs in metrics.items()},
                single_client_test_events=[dict(round=r,client=c["client"],max=c["largest_cluster_fraction"])
                                          for r,cs in metrics.items() for c in cs if c["occupied_clusters"] == 1],
                late_probe_max_peak=max(c[stage]["public"]["largest_cluster_fraction"]
                                        for d in late for c in d["clients"] for stage in ("T0","T1","T2")))


def main():
    out = Path(__file__).resolve().parent
    results = ROOT/"experiments/private_prior/results_full"
    completed = read(results/"completed.json")
    assert completed["runs"] == 4
    for name, expected in completed["files"].items():
        assert digest(results/name) == expected, name
    assert read(results/"finished.json")["completed_manifest_sha256"] == digest(results/"completed.json")
    assert {p.name for p in (results/"runs").glob("*.json")} == {c["case_id"]+".json" for c in CASES}
    env = read(results/"environment.json")
    assert env["preset"] == "full"
    environment_check(env)
    decisions = read(results/"decision.json")
    checked = []
    for case in CASES:
        entry = env["inputs"][case["case_id"]]
        assert digest(Path(entry["path"])/"prepared.json") == entry["metadata_sha256"]
        verify_cache(Path(entry["path"]), spec("full").config, case["seed"],
                     case["partition"], profile="strong", fixture=False)
        record = read(results/"runs"/(case["case_id"]+".json"))
        baseline = read(entry["baseline"])
        verify(record,case,entry,"full",True)
        verify(baseline,case,entry,"full",False)
        new, old = summarize(record), summarize(baseline)
        change = [100*(new["final_tests"][c]["acc"]-old["final_tests"][c]["acc"]) for c in range(6)]
        drop = [100*(old["late_rates"][c]-new["late_rates"][c]) for c in (0,3)]
        mean_drop = statistics.mean(drop)
        acc_delta = 100*(new["final_mean"]["acc"]-old["final_mean"]["acc"])
        passed = mean_drop >= 10 and min(drop) > 0 and new["healthy"] and acc_delta >= -1
        reported = next(r for r in decisions["cases"] if r["case_id"] == case["case_id"])
        assert abs(reported["improvement_pp"]-mean_drop) < 1e-10
        assert abs(reported["acc_change_pp"]-acc_delta) < 1e-10
        assert reported["passed"] == passed
        checked.append(dict(**case, old=old, new=new, mean_drop_pp=mean_drop,
                            small_drop_pp=drop, acc_delta_pp=acc_delta, acc_per_client_delta_pp=change, passed=passed))
    assert decisions["all_passed"] == all(c["passed"] for c in checked)
    (out/"audit.json").write_text(json.dumps(dict(seals_verified=True, sources_verified=True,
                                                 cases=checked),indent=2)+"\n",encoding="utf-8")
    for c in checked:
        print(c["case_id"],"late small",round(c["old"]["small_late"]*100,2),
              "->",round(c["new"]["small_late"]*100,2),"passed",c["passed"])
        print("last teacher %",[round(x*100,2) for x in c["new"]["final_teacher_rates"]],
              "last test max %",[round(x["largest_cluster_fraction"]*100,2) for x in c["new"]["final_tests"]])
        print("ACC deltas pp",c["acc_per_client_delta_pp"],"early",c["new"]["early_events"],
              "singles",c["new"]["single_client_test_events"])


if __name__ == "__main__":
    main()
