"""Measure old D and endpoint-bias D with paired, independent replay processes."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

for variable in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "LOKY_MAX_CPU_COUNT"):
    os.environ[variable] = "1"

import torch
from threadpoolctl import threadpool_limits

from experiments.snapshot_certification_timing.design import ROOT, environment, read, receipt, require, seal, sealed, sha, write
from experiments.snapshot_graph_scaling.design import cell_id
from experiments.snapshot_graph_scaling.inputs import raw_sha
from ..confirmation.run import design as trace_design, trace_record
from .report import build
from .worker import METHODS, replay


PACKAGE = Path(__file__).resolve().parent
NUMERICAL_SOURCES = ("experiments/public_scaling/certification.py",
                     "snapshot_routing/bias_numerical/candidate.py")


def schedule(preset):
    cases, _, _ = trace_design(preset)
    if preset == "smoke":
        cases = [case for case in cases if case["public_size"] == 64]
    blocks = []
    for index, case in enumerate(cases):
        for repeat in range(1, 4 if preset == "full" else 2):
            order = ["old", "new"] if (index + repeat) % 2 else ["new", "old"]
            blocks.append(dict(case=case, repeat=repeat, order=order))
    return cases, blocks


def numerical_result(root):
    path = root / "completed.json"
    if not path.exists():
        return dict(status="未核实", source=str(root))
    result = sealed(path)
    manifest = root / "manifest.json"
    require(result["preset"] == "full" and result["manifest"] == sha(manifest),
            "Numerical prerequisite has the wrong matrix or manifest")
    hashes = read(manifest)["sources"]
    candidate = "snapshot_routing/bias_numerical/candidate.py"
    core = "experiments/public_scaling/endpoint_bias.py"
    expected = hashes.get(core, hashes[candidate])
    require(expected == sha(ROOT / core) and hashes[NUMERICAL_SOURCES[0]] == sha(ROOT / NUMERICAL_SOURCES[0]),
            "The numerical audit used a different old or new D implementation")
    return dict(status="通过" if result["passed"] else "未通过", source=str(root),
                completed_sha=sha(path), failures=result["failures"])


def source_traces(root, cases, preset):
    manifest = root / "manifest.json"
    complete = sealed(root / "completed.json")
    identity = sha(manifest)
    require(complete["manifest"] == identity and read(manifest)["preset"] == preset,
            "Wrong archived E42 trace set")
    traces = {}
    for case in cases:
        cell = cell_id(case)
        path, ref = trace_record(root, case, identity, preset)
        record_sha = sha(path.with_suffix(".json"))
        require(ref["status"] == "captured" and complete["traces"][cell] == record_sha
                and raw_sha(path) == ref["payload_sha256"], f"Invalid archived trace: {cell}")
        traces[cell] = dict(path=str(path), sha=ref["payload_sha256"], record_sha=record_sha,
                            rounds=ref["cfg"]["rounds"], comparisons=ref["comparisons"])
    return traces


def run_path(out, block, method):
    return out / "runs" / f"{cell_id(block['case'])}_r{block['repeat']}_{method}.json"


def worker(out, index, method):
    marker = out / "manifest.json"
    manifest = read(marker)
    require(manifest["environment"] == environment(), "Worker environment differs")
    block = manifest["schedule"][index]
    cell = cell_id(block["case"])
    source = manifest["traces"][cell]
    path = Path(source["path"])
    record_path = path.with_suffix(".json")
    require(sha(record_path) == source["record_sha"] and raw_sha(path) == source["sha"], "Source trace changed")
    reference = sealed(record_path)
    result = replay(path, reference["cfg"], reference["traffic"], method, profile=block["repeat"] == 1)
    if block["repeat"] == 1 and not any(any(row["mismatches"]) for row in result["rows"]):
        require(result["traffic_rounds_equal_b"] == source["rounds"],
                "Identical relations did not reproduce E42 traffic")
    seal(run_path(out, block, method), dict(manifest=sha(marker), trace_sha=source["sha"], cell=cell,
                                          method=method, repeat=block["repeat"], case=block["case"], **result))


def execute(out, opts):
    cases, blocks = schedule(opts.preset)
    traces = source_traces(opts.trace_root, cases, opts.preset)
    numerical = numerical_result(opts.numerical_output)
    sources = [*sorted(PACKAGE.glob("*.py")), PACKAGE / "README.md", PACKAGE.parent / "report.py",
               *(ROOT / name for name in NUMERICAL_SOURCES), ROOT / "experiments/public_scaling/endpoint_bias.py"]
    manifest = dict(preset=opts.preset, schedule=blocks, traces=traces, numerical=numerical,
                    sources={path.relative_to(ROOT).as_posix(): sha(path) for path in sources},
                    environment=environment())
    marker = out / "manifest.json"
    if marker.exists():
        require(opts.resume and read(marker) == manifest, "Resume requires identical inputs, code and runtime")
    else:
        require(not out.exists() or (out.is_dir() and not any(out.iterdir())), "Use an empty output directory")
        write(marker, manifest)
    identity = sha(marker)
    done_path = out / "completed.json"
    previous_done = sealed(done_path) if receipt(done_path).exists() else None
    block_hashes, runs = {}, []
    for index, block in enumerate(blocks):
        cell = cell_id(block["case"])
        source = traces[cell]
        pair_path = out / "pairs" / f"{cell}_r{block['repeat']}.json"
        previous = sealed(pair_path) if receipt(pair_path).exists() else None
        hashes = {}
        for method in block["order"]:
            path = run_path(out, block, method)
            if previous is None:
                require(previous_done is None, "Completed experiment lost a pair")
                print(f"Pair {index + 1}/{len(blocks)} {cell} r{block['repeat']} {method}", flush=True)
                subprocess.run([sys.executable, "-B", "-m", "snapshot_routing.bias_resources.run",
                                "--output", str(out), "--worker", str(index), method], cwd=ROOT, check=True)
            result = sealed(path)
            require((result["manifest"], result["trace_sha"], result["cell"], result["case"], result["repeat"],
                     result["method"], result["edge_comparisons"])
                    == (identity, source["sha"], cell, block["case"], block["repeat"], method, source["comparisons"])
                    and [r["round"] for r in result["rows"]] == list(range(1, source["rounds"] + 1)),
                    f"Invalid replay: {path}")
            runs.append(result)
            hashes[path.relative_to(out).as_posix()] = sha(path)
        pair = dict(manifest=identity, block=block, runs=hashes)
        if previous is None:
            seal(pair_path, pair)
        else:
            require(previous == pair, "Paired results changed")
        block_hashes[pair_path.relative_to(out).as_posix()] = sha(pair_path)
    result = build(out, opts.preset, runs, numerical)
    complete = dict(manifest=identity, pairs=block_hashes, numerical=numerical, **result)
    require(previous_done is None or previous_done == complete, "Completed experiment changed")
    seal(done_path, complete)
    print(f"Finished: {out / 'report.md'}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=("full", "smoke"), default="full")
    parser.add_argument("--trace-root", type=Path)
    parser.add_argument("--numerical-output", type=Path, default=ROOT / "outputs/snapshot_routing_bias_numerical_full")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--worker", nargs=2, help=argparse.SUPPRESS)
    opts = parser.parse_args()
    out = (opts.output or ROOT / "outputs" / f"snapshot_routing_bias_resources_{opts.preset}").resolve()
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        if opts.worker:
            index, method = opts.worker
            require(method in METHODS and int(index) >= 0, "Invalid worker arguments")
            worker(out, int(index), method)
            return
        trace_dir = ("snapshot_routing_confirmation_full" if opts.preset == "full"
                     else "snapshot_routing_confirmation_release_smoke")
        opts.trace_root = (opts.trace_root or ROOT / "outputs" / trace_dir).resolve()
        opts.numerical_output = opts.numerical_output.resolve()
        for source in (opts.trace_root, opts.numerical_output):
            require(not (out.is_relative_to(source) or source.is_relative_to(out)), "Output overlaps an input")
        execute(out, opts)


if __name__ == "__main__":
    main()
