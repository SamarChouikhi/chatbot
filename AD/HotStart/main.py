"""
HotStart anomaly detection — CLI entry point.

Usage:
    python main.py --domain energy
    python main.py --domain water
    python main.py --domain energy --data path/to/energy.csv --output-dir results/energy
    python main.py --domain water  --data path/to/water.csv  --output-dir results/water
"""

from __future__ import annotations

import argparse


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="HotStart — Chronos-based IoT anomaly detection"
    )
    p.add_argument(
        "--domain",
        default="energy",
        choices=["energy", "water", "gaz", "fuel"],
        help="Domain to analyse (default: energy)",
    )
    p.add_argument("--data", default=None, metavar="CSV", help="Override CSV path")
    p.add_argument("--output-dir", default=None, metavar="DIR", help="Override output dir")
    p.add_argument(
        "--device",
        default=None,
        choices=["cpu", "cuda", "mps"],
        help="Torch device (default from config)",
    )
    p.add_argument(
        "--no-plots",
        action="store_true",
        help="Skip PNG generation (faster, for API/production use)",
    )
    p.add_argument(
        "--retrain",
        action="store_true",
        help="Job B : fine-tune Chronos (tous les devices) puis lance la détection (Job A)",
    )
    p.add_argument(
        "--retrain-only",
        action="store_true",
        help="Job B uniquement : fine-tune Chronos sans lancer la détection",
    )
    return p


def main() -> None:
    args = _build_parser().parse_args()

    if args.domain == "water":
        from water.config import WaterConfig
        from water.pipeline import run
        cfg = WaterConfig.from_file()
    elif args.domain == "gaz":
        from gaz.config import GazConfig
        from gaz.pipeline import run
        cfg = GazConfig.from_file()
    elif args.domain == "fuel":
        from fuel.config import FuelConfig
        from fuel.pipeline import run
        cfg = FuelConfig.from_file()
    else:
        from energy.config import EnergyConfig
        from energy.pipeline import run
        cfg = EnergyConfig.from_file()

    if args.data:
        cfg.data_path = args.data
    if args.output_dir:
        cfg.output_dir = args.output_dir
    if args.device:
        cfg.device = args.device

    # ── Job B — Retraining mensuel ────────────────────────────────────────
    if args.retrain or args.retrain_only:
        if args.domain == "water":
            from water.retrain_job import run_retrain
        else:
            from energy.retrain_job import run_retrain
        run_retrain(cfg)

    # ── Job A — Détection ─────────────────────────────────────────────────
    if not args.retrain_only:
        run(cfg, generate_plots=not args.no_plots)

    try:
        import gc
        import torch
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
        gc.collect()
    except Exception:
        pass


if __name__ == "__main__":
    main()
