"""Four quality-only B interventions with a frozen paired historical reference."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from experiments.public_scaling.data import runtime
from experiments.stl10_transfer.run import digest, seal, write_new
from experiments.quantity_heterogeneity import data
from experiments.local_public_lr import run as old_run, engine as old_engine, probes
from . import engine
from .design import CASES, spec
from .report import report
from .training import log_prior

ROOT = Path(__file__).resolve().parents[2]
DIR = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_bytes())


def sources():
    values = old_run.sources()
    for path in sorted(DIR.glob("*.py")):
        values[str(path.relative_to(ROOT))] = digest(path)
    values[str((DIR/"PREREGISTRATION.md").relative_to(ROOT))] = digest(DIR/"PREREGISTRATION.md")
    return values


def environment_check(env):
    if env["sources"] != sources() or env["spec"] != spec(env["preset"]).json():
        raise ValueError("Frozen source or configuration changed")
    now = runtime()
    if any(env["runtime"].get(k) != now.get(k) for k in
           ("python", "executable", "numpy", "scipy", "sklearn", "torch", "platform")):
        raise ValueError("Runtime changed")
    if env["cases"] != list(CASES):
        raise ValueError("Frozen case matrix changed")


def meta(case):
    return dict(case, branch="local_lr", profile="strong", method="B", clients=6)


def verify(record, case, entry, preset, corrected):
    cfg = spec(preset)
    old_run.verify_record(record, meta(case), cfg, entry, preset == "smoke")
    baseline = read(entry["baseline"])
    if digest(entry["baseline"]) != entry["baseline_sha256"]:
        raise ValueError("Historical paired reference changed")
    for field in ("initial_head_digest", "graph_sha256", "probe_manifest", "public_client_weights"):
        if record[field] != baseline[field]:
            raise ValueError("Paired identity mismatch: " + field)
    for row, ref in zip(record["round_records"], baseline["round_records"]):
        for key in ("private_subset_digest", "private_subset_pseudo_histograms", "private_optimizer_steps",
                    "private_forward_endpoints", "public_optimizer_steps", "public_edges_consumed",
                    "student_forward_endpoints", "public_schedule_digest"):
            if row[key] != ref[key]:
                raise ValueError("Paired work/order mismatch: " + key)
    if corrected:
        expected = {str(c): log_prior(np.load(Path(entry["path"])/f"client_{c}_pseudo.npy",
                                             allow_pickle=False), cfg.config.classes).tolist() for c in (0,3)}
        if record.get("private_correction") != dict(clients=[0,3], log_priors=expected,
                                                    inference="raw logits", private_loss="Balanced Softmax"):
            raise ValueError("Private correction identity mismatch")


def inputs(env, out):
    cfg, preset = spec(env["preset"]), env["preset"]
    references = {}
    for case in CASES:
        cid = case["case_id"]
        if preset == "smoke":
            from .fixture import prepare
            directory = prepare(DIR/"prepared_smoke", DIR/"fixture_data", cfg,
                                case["seed"], case["partition"])
            baseline_path = out/"references"/(cid+".json")
            if not baseline_path.exists():
                with threadpool_limits(limits=1):
                    baseline = old_engine.run(directory, cfg, branch="local_lr", fixture=True, progress=False)
                write_new(baseline_path, seal(baseline))
            baseline = read(baseline_path)
        else:
            history = ROOT/"experiments"/("local_public_lr" if cid == "strong_iid_seed1001"
                                          else "local_public_lr_confirmation")/"results_full"
            baseline_path = history/"runs"/(cid+"_local_lr.json")
            baseline = read(baseline_path)
            completed = read(history/"completed.json")
            files = {name.replace("\\","/"): value for name,value in completed["files"].items()}
            if files.get("runs/"+baseline_path.name) != digest(baseline_path):
                raise ValueError("Reference differs from historical completion manifest")
            if read(history/"finished.json")["completed_manifest_sha256"] != digest(history/"completed.json"):
                raise ValueError("Historical completion seal differs")
            directory = Path(baseline["prepared_directory"])
        data.verify(directory, cfg.config, case["seed"], case["partition"], profile="strong", fixture=preset=="smoke")
        public_ids = np.load(directory/"public_ids.npy", allow_pickle=False)[:cfg.config.samples]
        probe = probes.manifest(case["seed"], public_ids, 32 if preset == "smoke" else 512)
        entry = dict(path=str(directory.resolve()), metadata_sha256=digest(directory/"prepared.json"),
                     probe_manifest=probe, baseline=str(baseline_path.resolve()), baseline_sha256=digest(baseline_path))
        if cid in env["inputs"] and env["inputs"][cid] != entry:
            raise ValueError("Frozen input/reference pointer changed")
        verify(baseline, case, entry, preset, False)
        for c in (0,3):
            log_prior(np.load(directory/f"client_{c}_pseudo.npy", allow_pickle=False), cfg.config.classes)
        references[cid] = entry
    env["inputs"] = references
    write_new(out/"environment.json", env)


def worker(env, out, index):
    environment_check(env)
    case = CASES[index]
    entry = env["inputs"][case["case_id"]]
    if digest(Path(entry["path"])/"prepared.json") != entry["metadata_sha256"]:
        raise ValueError("Prepared metadata changed")
    # Input data.verify in the engine rechecks the complete cached feature files.
    with threadpool_limits(limits=1):
        record = engine.run(entry["path"], spec(env["preset"]), branch="local_lr",
                            fixture=env["preset"] == "smoke")
    record["private_correction"] = dict(clients=[0,3], log_priors={
        str(c): log_prior(np.load(Path(entry["path"])/f"client_{c}_pseudo.npy", allow_pickle=False), 10).tolist()
        for c in (0,3)}, inference="raw logits", private_loss="Balanced Softmax")
    record = seal(record)
    verify(record, case, entry, env["preset"], True)
    write_new(out/"runs"/(case["case_id"]+".json"), record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=("full","smoke"), default="full")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--worker", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    out = (args.output or DIR/("results_"+args.preset)).resolve()
    if args.worker is not None:
        worker(read(out/"environment.json"), out, args.worker)
        return
    if args.resume:
        env = read(out/"environment.json")
        if args.preset != env["preset"]:
            raise ValueError("Resume preset mismatch")
        environment_check(env)
    else:
        if out.exists() and any(out.iterdir()):
            raise FileExistsError("Use --resume or an empty output directory")
        env = dict(preset=args.preset, spec=spec(args.preset).json(), cases=list(CASES),
                   sources=sources(), runtime=runtime(), inputs={})
    out.mkdir(parents=True, exist_ok=True)
    write_new(out/"environment.json", env)
    inputs(env, out)
    entries = []
    for index, case in enumerate(CASES):
        path = out/"runs"/(case["case_id"]+".json")
        if not path.exists():
            print("Running "+case["case_id"], flush=True)
            subprocess.run([sys.executable, "-m", "experiments.private_prior.run",
                            "--preset", env["preset"], "--output", str(out), "--worker", str(index)],
                           cwd=ROOT, check=True)
        record = read(path)
        entry = env["inputs"][case["case_id"]]
        verify(record, case, entry, env["preset"], True)
        entries.append((case, record, read(entry["baseline"])))
    environment_check(env)
    inputs(env, out)
    report(out, entries, smoke=env["preset"]=="smoke")
    write_new(out/"completed.json", dict(runs=4, files={
        str(p.relative_to(out)).replace("\\","/"): digest(p) for p in sorted(out.rglob("*"))
        if p.is_file() and p.name not in ("completed.json","finished.json")}))
    write_new(out/"finished.json", dict(completed_manifest_sha256=digest(out/"completed.json")))
    print("Finished: "+str(out), flush=True)


if __name__ == "__main__":
    main()
