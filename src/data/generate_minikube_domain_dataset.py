import argparse
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


SCENARIO_COUNTS = {
    "normal_idle": ("normal", 3000),
    "normal_light_workload": ("normal", 2500),
    "normal_medium_workload": ("normal", 1500),
    "cpu_stress": ("anomaly", 1000),
    "memory_stress": ("anomaly", 1000),
    "cpu_memory_stress": ("anomaly", 800),
    "oom_pressure": ("anomaly", 200),
}


def repeat_rows(df: pd.DataFrame, n: int) -> pd.DataFrame:
    reps = math.ceil(n / len(df))
    return pd.concat([df] * reps, ignore_index=True).iloc[:n].copy()


def load_live_minikube_stats(live_path: str):
    path = Path(live_path)

    fallback = {
        "cpu_mean": 0.025,
        "memory_mean": 0.050,
        "cpu_std": 0.006,
        "memory_std": 0.002,
        "source": "fallback_observed_minikube_values",
    }

    if not path.exists():
        return fallback

    df = pd.read_csv(path)

    cpu_col = "cpu_usage" if "cpu_usage" in df.columns else "CPU (%)"
    mem_col = "memory_usage" if "memory_usage" in df.columns else "MEM (%)"

    if "label" in df.columns:
        normal_df = df[df["label"].astype(str).str.lower() == "normal"].copy()
        if len(normal_df) >= 5:
            df = normal_df

    if len(df) < 5:
        return fallback

    cpu_std = float(df[cpu_col].std())
    mem_std = float(df[mem_col].std())

    return {
        "cpu_mean": float(df[cpu_col].mean()),
        "memory_mean": float(df[mem_col].mean()),
        "cpu_std": max(cpu_std, 0.003),
        "memory_std": max(mem_std, 0.0015),
        "source": str(path),
    }


def get_vm_stats(vm_df: pd.DataFrame):
    return {
        "cpu_mean": float(vm_df["CPU (%)"].mean()),
        "cpu_std": float(vm_df["CPU (%)"].std()),
        "memory_mean": float(vm_df["MEM (%)"].mean()),
        "memory_std": float(vm_df["MEM (%)"].std()),
    }


def z_align(values, source_mean, source_std, target_mean, target_std):
    z = (values - source_mean) / max(source_std, 1e-9)
    return target_mean + z * target_std


def smooth_noise(rng, n, scale):
    raw = rng.normal(0, scale, size=n)
    return pd.Series(raw).rolling(5, min_periods=1, center=True).mean().to_numpy()


def transform_block(block, scenario, vm_stats, live_stats, rng):
    n = len(block)

    cpu_target_std = max(live_stats["cpu_std"], live_stats["cpu_mean"] * 0.20, 0.003)
    mem_target_std = max(live_stats["memory_std"], live_stats["memory_mean"] * 0.04, 0.0015)

    base_cpu = z_align(
        block["CPU (%)"].to_numpy(),
        vm_stats["cpu_mean"],
        vm_stats["cpu_std"],
        live_stats["cpu_mean"],
        cpu_target_std,
    )

    base_mem = z_align(
        block["MEM (%)"].to_numpy(),
        vm_stats["memory_mean"],
        vm_stats["memory_std"],
        live_stats["memory_mean"],
        mem_target_std,
    )

    t = np.linspace(0, 1, n)

    if scenario == "normal_idle":
        cpu = base_cpu + smooth_noise(rng, n, live_stats["cpu_mean"] * 0.04)
        mem = base_mem + smooth_noise(rng, n, live_stats["memory_mean"] * 0.01)

    elif scenario == "normal_light_workload":
        cpu = base_cpu + live_stats["cpu_mean"] * (0.35 + 0.15 * np.sin(2 * np.pi * t))
        mem = base_mem + live_stats["memory_mean"] * 0.10

    elif scenario == "normal_medium_workload":
        cpu = base_cpu + live_stats["cpu_mean"] * (1.10 + 0.25 * np.sin(4 * np.pi * t))
        mem = base_mem + live_stats["memory_mean"] * 0.25

    elif scenario == "cpu_stress":
        cpu = live_stats["cpu_mean"] * (4.0 + 5.0 * t) + smooth_noise(rng, n, 0.015)
        mem = base_mem + live_stats["memory_mean"] * 0.25

    elif scenario == "memory_stress":
        cpu = base_cpu + live_stats["cpu_mean"] * 0.50
        mem = live_stats["memory_mean"] * (2.0 + 7.0 * t) + smooth_noise(rng, n, 0.008)

    elif scenario == "cpu_memory_stress":
        cpu = live_stats["cpu_mean"] * (4.0 + 6.0 * t) + smooth_noise(rng, n, 0.015)
        mem = live_stats["memory_mean"] * (2.5 + 8.0 * t) + smooth_noise(rng, n, 0.008)

    elif scenario == "oom_pressure":
        cpu = live_stats["cpu_mean"] * (2.0 + 2.0 * np.sin(3 * np.pi * t))
        mem = np.linspace(
            max(live_stats["memory_mean"] * 4, 0.20),
            max(live_stats["memory_mean"] * 12, 0.65),
            n,
        ) + smooth_noise(rng, n, 0.01)

    else:
        raise ValueError(f"Unknown scenario: {scenario}")

    block["CPU (%)"] = np.clip(cpu, 0.0, 0.95)
    block["MEM (%)"] = np.clip(mem, 0.0, 0.95)

    # Keep non-core telemetry plausible.
    if "Energy (watts)" in block.columns:
        block["Energy (watts)"] = 60 + block["CPU (%)"] * 120 + rng.normal(0, 2, size=n)

    if "rx (B/sec)" in block.columns:
        block["rx (B/sec)"] = np.maximum(0, block["rx (B/sec)"] * rng.uniform(0.10, 0.35))

    if "tx (B/sec)" in block.columns:
        block["tx (B/sec)"] = np.maximum(0, block["tx (B/sec)"] * rng.uniform(0.10, 0.35))

    if "fs (%)" in block.columns:
        block["fs (%)"] = np.clip(block["fs (%)"], 0.0, 1.0)

    return block


def generate_dataset(source_csv, live_csv, output_csv, rows, seed):
    rng = np.random.default_rng(seed)

    df = pd.read_csv(source_csv)

    required_cols = ["node_name", "timestamp", "CPU (%)", "MEM (%)"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in source CSV: {missing}")

    vm_df = df[df["node_name"] == "vm-node"].copy()
    if vm_df.empty:
        raise ValueError("No rows found for node_name='vm-node'")

    vm_df = vm_df.sort_values("timestamp").reset_index(drop=True)

    vm_stats = get_vm_stats(vm_df)
    live_stats = load_live_minikube_stats(live_csv)

    print("VM-node stats:")
    print(vm_stats)
    print("Target Minikube stats:")
    print(live_stats)

    all_blocks = []
    current_time = pd.Timestamp(datetime.now(timezone.utc)).floor("30s")

    total_plan_rows = sum(count for _, count in SCENARIO_COUNTS.values())
    if rows != total_plan_rows:
        print(f"Warning: current scenario plan is fixed at {total_plan_rows} rows. Ignoring --rows={rows}.")

    cursor = 0

    for scenario, (label, count) in SCENARIO_COUNTS.items():
        block = repeat_rows(vm_df, count)
        block = transform_block(block, scenario, vm_stats, live_stats, rng)

        timestamps = pd.date_range(
            start=current_time + pd.Timedelta(seconds=30 * cursor),
            periods=count,
            freq="30s",
        )

        block["timestamp"] = timestamps.astype(str)
        block["node_name"] = "minikube"
        block["scenario"] = scenario
        block["label"] = label
        block["is_synthetic"] = 1
        block["source_domain"] = "vm-node"
        block["target_domain"] = "minikube"
        block["source_row_index"] = np.arange(count)

        all_blocks.append(block)
        cursor += count

    out = pd.concat(all_blocks, ignore_index=True)

    # Add model-friendly aliases too.
    out["cpu_usage"] = out["CPU (%)"]
    out["memory_usage"] = out["MEM (%)"]

    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)

    print("-" * 60)
    print(f"Saved: {output_path}")
    print(f"Shape: {out.shape}")
    print(out.groupby(["scenario", "label"]).size())
    print("-" * 60)
    print(out[["CPU (%)", "MEM (%)"]].describe())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="data/raw/node_telemetry_pods_on.csv")
    parser.add_argument("--live", default="data/live/minikube_dataset.csv")
    parser.add_argument("--output", default="data/processed/minikube_domain_10000.csv")
    parser.add_argument("--rows", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()

    generate_dataset(
        source_csv=args.source,
        live_csv=args.live,
        output_csv=args.output,
        rows=args.rows,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()



