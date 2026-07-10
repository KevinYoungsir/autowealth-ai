"""Run the configured real-data A-share research pipeline on explicit request."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autowealth.research.real_pipeline import (
    RealDataAccessError,
    RealResearchError,
    run_real_data_research,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a reproducible real-data A-share research experiment."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the YAML research configuration.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = run_real_data_research(args.config)
    except RealDataAccessError as exc:
        print(f"Real market data could not be loaded: {exc}", file=sys.stderr)
        return 2
    except RealResearchError as exc:
        print(f"Research run failed: {exc}", file=sys.stderr)
        return 1
    except (OSError, RuntimeError) as exc:
        print(f"Research artifacts could not be completed: {exc}", file=sys.stderr)
        return 1

    print(f"run_id: {result.run_id}")
    print(f"run_directory: {result.run_directory}")
    print("metrics:")
    print(json.dumps(result.metrics, ensure_ascii=False, indent=2, default=str))
    print(f"warnings: {len(result.warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
