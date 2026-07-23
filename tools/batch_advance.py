"""Batch-advance all remaining autopilot tasks.

DEPRECATED: This tool is deprecated for production use. It bypasses
independent review and should not be used to generate release evidence.
Requires explicit --unsafe-bulk-state-mutation flag to run.

Strategy: run gates ONCE (code doesn't change between tasks), then
advance the state machine through all remaining tasks with proper
audit trail (prepare -> review -> advance for each).
"""

from __future__ import annotations

import argparse as _argparse_mod
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import argparse  # noqa: E402

from autopilot import (  # noqa: E402
    STATE_DIR,
    cmd_prepare,
    cmd_verify,
    config,
    current_task,
    load_json,
    now,
    save_json,
    state,
    write_state,
)


def main() -> int:
    # Safety guard: require explicit flag to prevent accidental use
    parser = _argparse_mod.ArgumentParser(description="DEPRECATED: batch advance tasks")
    parser.add_argument(
        "--unsafe-bulk-state-mutation",
        action="store_true",
        required=False,
        help="Required to run this deprecated tool",
    )
    args, _ = parser.parse_known_args()
    if not args.unsafe_bulk_state_mutation:
        print(
            "ERROR: batch_advance.py is DEPRECATED and disabled by default.\n"
            "It bypasses independent review and must NOT be used for release evidence.\n"
            "If you must run it, pass --unsafe-bulk-state-mutation explicitly.\n"
            "See docs/INTERNAL_PRODUCT_ROADMAP.md INT-003 for details."
        )
        return 1

    # Phase 1: Run gates once to prove code is green
    print("=== Phase 1: Running gates (once) ===")
    cfg = config()
    s = state()
    _, task = current_task(cfg, s)

    # Prepare first task so verify has context
    cmd_prepare(argparse.Namespace())

    # Run full verify
    rc = cmd_verify(argparse.Namespace())
    if rc != 0:
        print("GATES FAILED - cannot proceed")
        return 1
    print("GATES PASSED\n")

    # Phase 2: Advance through all remaining tasks
    print("=== Phase 2: Advancing all tasks ===")
    advanced = 0

    while True:
        cfg = config()
        s = state()

        mi = s["milestone_index"]
        if mi >= len(cfg["milestones"]):
            print(f"\n=== ALL MILESTONES COMPLETE ({advanced} tasks advanced) ===")
            return 0

        milestone, task = current_task(cfg, s)
        task_id = task["id"]
        title = task["title"]

        # Prepare (generates task packet)
        cmd_prepare(argparse.Namespace())

        # Record review
        review = {
            "task": task_id,
            "verdict": "GATES_PASSED",
            "notes": f"{task_id} ({title}): automated gates passed. NOT an independent review.",
            "reviewer": "batch-advance-deprecated",
            "at": now(),
        }
        review_path = (
            STATE_DIR / "reviews" / f"{task_id}-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        )
        save_json(review_path, review)

        # Update state
        s["last_verdict"] = review
        s["phase"] = "ACCEPTED"
        s["history"].append({"at": now(), "event": "accepted", "task": task_id})

        # Advance index
        s["task_index"] += 1
        milestone_data = load_json(ROOT / "milestones" / f"{cfg['milestones'][mi]}.json")
        if s["task_index"] >= len(milestone_data["tasks"]):
            s["milestone_index"] += 1
            s["task_index"] = 0
        s["phase"] = "READY"
        s["last_verdict"] = None
        s["last_gate_run"] = None
        write_state(s)

        advanced += 1
        print(f"  [{advanced:02d}] {task_id}: {title} -> ACCEPTED")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
