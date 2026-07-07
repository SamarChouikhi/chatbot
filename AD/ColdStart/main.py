"""
ARIA — Cold Start Anomaly Detection
Usage:
    # Energy (défaut)
    python main.py
    python main.py --domain energy --device NEW_DEVICE_002 --phases L1 L2 L3
    python main.py --domain energy --device NEW_DEV --data /path/new.csv
    python main.py --domain energy --compare-hot ../HotStart/outputs/energy/anomalies_result.csv

    # Water
    python main.py --domain water
    python main.py --domain water --device NEW_WATER_001
    python main.py --domain water --data /path/new_water.csv
    python main.py --domain water --compare-hot ../HotStart/outputs/water/anomalies_result.csv

    # Options communes
    python main.py --domain energy --algo zscore --synthetic-only
    python main.py --domain water  --algo ensemble --output results/test
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="ARIA Cold Start — Anomaly detection for new IoT devices with no history",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--domain",
        choices=["energy", "water", "gaz", "fuel"],
        default="energy",
        help="IoT domain to analyze (default: energy)",
    )
    p.add_argument(
        "--config",
        default=None,
        help="Path to a YAML config file (default: <domain>/config.yaml)",
    )
    p.add_argument(
        "--device",
        default=None,
        help="Override new_device_id from config",
    )
    p.add_argument(
        "--phases",
        nargs="+",
        default=None,
        help="Energy only — override phases (e.g. --phases L1 L2 L3)",
    )
    p.add_argument(
        "--data",
        default=None,
        help="Path to real data CSV for the new device (optional)",
    )
    p.add_argument(
        "--population",
        default=None,
        help="Override path to population CSV (existing devices data)",
    )
    p.add_argument(
        "--output",
        default=None,
        help="Override output directory",
    )
    p.add_argument(
        "--algo",
        choices=["zscore", "iqr", "isolation_forest", "ensemble"],
        default=None,
        help="Detection algorithm (default: ensemble)",
    )
    p.add_argument(
        "--compare-hot",
        metavar="HOT_RESULT_CSV",
        default=None,
        help="Path to a HotStart anomalies_result.csv for cold-vs-hot comparison",
    )
    p.add_argument(
        "--synthetic-only",
        action="store_true",
        help="Run detection on synthetic data only (ignores --data)",
    )
    return p.parse_args()


def _run_energy(args: argparse.Namespace) -> None:
    from energy.config import ColdStartAlgorithm, ColdStartConfig
    from energy.pipeline import run

    config = (
        ColdStartConfig.from_yaml(args.config)
        if args.config
        else ColdStartConfig.from_file()
    )

    if args.device:
        config.new_device_id = args.device
    if args.phases:
        config.new_device_phases = args.phases
    if args.data and not args.synthetic_only:
        config.new_device_data_path = args.data
    if args.synthetic_only:
        config.new_device_data_path = ""
    if args.population:
        config.population_data_path = args.population
    if args.output:
        config.output_dir = args.output
    if args.algo:
        config.algorithm = ColdStartAlgorithm(args.algo)

    config._validate()

    hot_result = None
    if args.compare_hot:
        import pandas as pd
        hot_path = Path(args.compare_hot)
        if hot_path.exists():
            hot_result = pd.read_csv(hot_path, parse_dates=[config.timestamp_col])
        else:
            print(f"[WARN] HotStart result not found: {hot_path}")

    run(config, hot_result=hot_result)


def _run_water(args: argparse.Namespace) -> None:
    from water.config import ColdStartAlgorithm, WaterColdStartConfig
    from water.pipeline import run

    config = (
        WaterColdStartConfig.from_yaml(args.config)
        if args.config
        else WaterColdStartConfig.from_file()
    )

    if args.device:
        config.new_device_id = args.device
    if args.phases:
        print("[WARN] --phases ignoré pour le domaine water (pas de dimension phase)")
    if args.data and not args.synthetic_only:
        config.new_device_data_path = args.data
    if args.synthetic_only:
        config.new_device_data_path = ""
    if args.population:
        config.population_data_path = args.population
    if args.output:
        config.output_dir = args.output
    if args.algo:
        config.algorithm = ColdStartAlgorithm(args.algo)

    config._validate()

    hot_result = None
    if args.compare_hot:
        import pandas as pd
        hot_path = Path(args.compare_hot)
        if hot_path.exists():
            hot_result = pd.read_csv(hot_path, parse_dates=[config.timestamp_col])
        else:
            print(f"[WARN] HotStart result not found: {hot_path}")

    run(config, hot_result=hot_result)


def _run_gaz(args: argparse.Namespace) -> None:
    from gaz.config import ColdStartAlgorithm, GazColdStartConfig
    from gaz.pipeline import run

    config = (
        GazColdStartConfig.from_yaml(args.config)
        if args.config
        else GazColdStartConfig.from_file()
    )

    if args.device:
        config.new_device_id = args.device
    if args.data and not args.synthetic_only:
        config.new_device_data_path = args.data
    if args.synthetic_only:
        config.new_device_data_path = ""
    if args.population:
        config.population_data_path = args.population
    if args.output:
        config.output_dir = args.output
    if args.algo:
        config.algorithm = ColdStartAlgorithm(args.algo)

    config._validate()

    hot_result = None
    if args.compare_hot:
        import pandas as pd
        hot_path = Path(args.compare_hot)
        if hot_path.exists():
            hot_result = pd.read_csv(hot_path, parse_dates=[config.timestamp_col])
        else:
            print(f"[WARN] HotStart result not found: {hot_path}")

    run(config, hot_result=hot_result)


def _run_fuel(args: argparse.Namespace) -> None:
    from fuel.config import ColdStartAlgorithm, FuelColdStartConfig
    from fuel.pipeline import run

    config = (
        FuelColdStartConfig.from_yaml(args.config)
        if args.config
        else FuelColdStartConfig.from_file()
    )
    if args.device:
        config.new_device_id = args.device
    if args.data and not args.synthetic_only:
        config.new_device_data_path = args.data
    if args.synthetic_only:
        config.new_device_data_path = ""
    if args.population:
        config.population_data_path = args.population
    if args.output:
        config.output_dir = args.output
    if args.algo:
        config.algorithm = ColdStartAlgorithm(args.algo)

    config._validate()

    hot_result = None
    if args.compare_hot:
        import pandas as pd
        hot_path = Path(args.compare_hot)
        if hot_path.exists():
            hot_result = pd.read_csv(hot_path, parse_dates=[config.timestamp_col])
        else:
            print(f"[WARN] HotStart result not found: {hot_path}")

    run(config, hot_result=hot_result)


def main() -> None:
    args = _parse_args()

    if args.domain == "water":
        _run_water(args)
    elif args.domain == "gaz":
        _run_gaz(args)
    elif args.domain == "fuel":
        _run_fuel(args)
    else:
        _run_energy(args)


if __name__ == "__main__":
    main()
