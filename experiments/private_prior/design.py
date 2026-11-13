from experiments.local_public_lr.design import plan as original_plan

CASES = tuple(dict(seed=seed, partition=partition,
                  case_id=f"strong_{partition}_seed{seed}")
              for seed in (1001, 1002) for partition in ("iid", "dirichlet_0.1"))


def spec(preset):
    return original_plan(preset)["local_lr"]
