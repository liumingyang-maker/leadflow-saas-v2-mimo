from __future__ import annotations

import argparse
import datetime as dt
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "autopilot.json"
EXAMPLE_CONFIG = ROOT / "config" / "autopilot.example.json"
STATE_DIR = ROOT / ".autopilot"
STATE_PATH = STATE_DIR / "state.json"


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict[str, Any]) -> None:
    """Atomically write JSON using temp file + os.replace()."""
    import os
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise SystemExit(
            f"Missing {CONFIG_PATH}. Copy {EXAMPLE_CONFIG.name} to autopilot.json first."
        )
    return load_json(CONFIG_PATH)


def initial_state(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "project": cfg["project_name"],
        "created_at": now(),
        "updated_at": now(),
        "milestone_index": 0,
        "task_index": 0,
        "phase": "READY",
        "last_verdict": None,
        "last_gate_run": None,
        "history": [],
    }


def state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        raise SystemExit("Autopilot not initialized. Run: python tools/autopilot.py init")
    return load_json(STATE_PATH)


def write_state(s: dict[str, Any]) -> None:
    s["updated_at"] = now()
    save_json(STATE_PATH, s)


def current_task(cfg: dict[str, Any], s: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    milestones = cfg["milestones"]
    mi = s["milestone_index"]
    if mi >= len(milestones):
        raise SystemExit("All milestones complete.")
    milestone = load_json(ROOT / "milestones" / f"{milestones[mi]}.json")
    ti = s["task_index"]
    if ti >= len(milestone["tasks"]):
        raise SystemExit("Milestone task index out of range.")
    return milestone, milestone["tasks"][ti]


def run(cmd: list[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    resolved = [sys.executable, *cmd[1:]] if cmd and cmd[0] == "python" else cmd
    return subprocess.run(resolved, cwd=ROOT, input=stdin, text=True, capture_output=True)


def ensure_git_repo() -> None:
    p = run(["git", "rev-parse", "--show-toplevel"])
    if p.returncode != 0:
        raise SystemExit("Copy the kit into a Git repository first.")
    if Path(p.stdout.strip()).resolve() != ROOT.resolve():
        raise SystemExit(f"Git root mismatch: expected {ROOT}, got {p.stdout.strip()}")


def cmd_init(_: argparse.Namespace) -> int:
    cfg = config()
    ensure_git_repo()
    for name in [
        "packets",
        "plans",
        "logs",
        "reviews",
        "evidence",
        "screenshots",
        "controller-output",
    ]:
        (STATE_DIR / name).mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        save_json(STATE_PATH, initial_state(cfg))
    print(f"Initialized {STATE_PATH}")
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    cfg = config()
    s = state()
    milestone, task = current_task(cfg, s)
    print(
        json.dumps(
            {
                "phase": s["phase"],
                "milestone": milestone["milestone"],
                "task": task,
                "last_verdict": s["last_verdict"],
                "last_gate_run": s["last_gate_run"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def render_packet(task: dict[str, Any]) -> str:
    gates = "\n".join(f"- {x}" for x in task["required_gates"])
    return f"""# Worker Task Packet

Task: {task["id"]}
Title: {task["title"]}
Category: {task["category"]}
Branch: {task["branch"]}
Worker: Reasonix/DeepSeek
Controller: Codex

## Mandatory context

- Read AGENTS.md
- Read docs/ARCHITECTURE.md
- Read docs/UI_SYSTEM.md for UI work
- Do not change product or architecture scope
- Do not commit, push, merge or deploy

## Goal

Implement exactly this task in the current V2 architecture.

## Required gates

{gates}

## Worker response

Return changed files, tests, commands, results, blockers and confirmation that no
Git release action occurred.
"""


def cmd_prepare(_: argparse.Namespace) -> int:
    cfg = config()
    s = state()
    _, task = current_task(cfg, s)
    path = STATE_DIR / "packets" / f"{task['id']}.md"
    path.write_text(render_packet(task), encoding="utf-8")
    s["phase"] = "PLANNING"
    s["history"].append({"at": now(), "event": "prepared", "task": task["id"]})
    write_state(s)
    print(path)
    return 0


def cmd_verify(_: argparse.Namespace) -> int:
    import platform

    cfg = config()
    s = state()
    _, task = current_task(cfg, s)
    results: dict[str, Any] = {}
    passed = True
    for name, command in cfg["gates"].items():
        p = run(command)
        results[name] = {
            "command": command,
            "returncode": p.returncode,
            "stdout": p.stdout[-12000:],
            "stderr": p.stderr[-12000:],
        }
        passed = passed and p.returncode == 0

    # Collect environment metadata for audit trail
    commit_sha = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    tree_sha = run(["git", "rev-parse", "HEAD^{tree}"]).stdout.strip()
    workspace_clean = run(["git", "status", "--porcelain"]).stdout.strip() == ""
    metadata = {
        "commit_sha": commit_sha,
        "tree_sha": tree_sha,
        "workspace_clean": workspace_clean,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = STATE_DIR / "evidence" / f"{task['id']}-gates-{stamp}.json"
    save_json(
        path,
        {"task": task["id"], "passed": passed, "metadata": metadata, "results": results},
    )
    s["last_gate_run"] = {"at": now(), "passed": passed, "path": str(path.relative_to(ROOT))}
    s["phase"] = "REVIEWING" if passed else "WORKER_FIX"
    write_state(s)
    print(json.dumps({"passed": passed, "evidence": str(path)}, indent=2))
    return 0 if passed else 1


def cmd_review(args: argparse.Namespace) -> int:
    cfg = config()
    s = state()
    _, task = current_task(cfg, s)
    verdict = args.verdict.upper()
    if verdict not in {"PASS", "FAIL"}:
        raise SystemExit("Verdict must be PASS or FAIL")
    review = {"task": task["id"], "verdict": verdict, "notes": args.notes, "at": now()}
    path = (
        STATE_DIR / "reviews" / f"{task['id']}-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    save_json(path, review)
    s["last_verdict"] = review
    s["phase"] = "ACCEPTED" if verdict == "PASS" else "WORKER_FIX"
    write_state(s)
    print(path)
    return 0


def cmd_advance(_: argparse.Namespace) -> int:
    cfg = config()
    s = state()
    milestone, task = current_task(cfg, s)
    gates = s.get("last_gate_run") or {}
    review = s.get("last_verdict") or {}
    if not gates.get("passed"):
        raise SystemExit("Cannot advance: latest gates did not pass.")
    if review.get("verdict") != "PASS" or review.get("task") != task["id"]:
        raise SystemExit("Cannot advance: current task review is not PASS.")
    s["history"].append({"at": now(), "event": "accepted", "task": task["id"]})
    s["task_index"] += 1
    if s["task_index"] >= len(milestone["tasks"]):
        s["milestone_index"] += 1
        s["task_index"] = 0
    s["phase"] = "READY"
    s["last_verdict"] = None
    s["last_gate_run"] = None
    write_state(s)
    print("Advanced.")
    return 0


def cmd_review_deepseek(args: argparse.Namespace) -> int:
    """调用 DeepSeek 进行审查"""
    from deepseek_reviewer import DeepSeekReviewer

    cfg = config()
    s = state()
    _, task = current_task(cfg, s)

    # 获取 diff
    diff_result = run(["git", "diff", "HEAD"])
    diff = diff_result.stdout

    # 获取任务上下文
    packet_path = STATE_DIR / "packets" / f"{task['id']}.md"
    context = packet_path.read_text(encoding="utf-8") if packet_path.exists() else ""

    reviewer = DeepSeekReviewer()

    if args.round == "all":
        results = reviewer.review_all(diff, context)
        all_pass = all(r.verdict == "PASS" for r in results.values())

        for round_name, result in results.items():
            print(f"{round_name}: {result.verdict}")
            if result.issues:
                for issue in result.issues:
                    print(f"  - {issue}")

        verdict = "PASS" if all_pass else "FAIL"
        notes = "\n".join(f"{r.round}: {r.notes}" for r in results.values())
    else:
        strict = args.round in ("architecture", "security", "release")
        result = reviewer.review(args.round, diff, context, strict)
        verdict = result.verdict
        notes = result.notes
        print(f"{args.round}: {verdict}")
        if result.issues:
            for issue in result.issues:
                print(f"  - {issue}")

    # 记录审查结果
    review = {
        "task": task["id"],
        "verdict": verdict,
        "notes": notes,
        "reviewer": "deepseek",
        "at": now(),
    }
    path = (
        STATE_DIR
        / "reviews"
        / f"{task['id']}-deepseek-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    save_json(path, review)
    s["last_verdict"] = review
    s["phase"] = "ACCEPTED" if verdict == "PASS" else "WORKER_FIX"
    write_state(s)

    return 0 if verdict == "PASS" else 1


def cmd_codex(args: argparse.Namespace) -> int:
    cfg = config()
    s = state()
    _, task = current_task(cfg, s)
    packet = STATE_DIR / "packets" / f"{task['id']}.md"
    if not packet.exists():
        cmd_prepare(argparse.Namespace())
    prompt = (ROOT / "MASTER_AUTOPILOT_PROMPT.md").read_text(encoding="utf-8")
    prompt += "\n\n# Current task packet\n\n" + packet.read_text(encoding="utf-8")
    command = cfg["controller"]["command"]
    if args.dry_run:
        print("COMMAND:", shlex.join(command))
        print(prompt)
        return 0
    p = run(command, stdin=prompt)
    out = (
        STATE_DIR
        / "controller-output"
        / f"{task['id']}-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
    )
    out.write_text(p.stdout + "\n\nSTDERR\n" + p.stderr, encoding="utf-8")
    print(p.stdout)
    if p.returncode:
        print(p.stderr, file=sys.stderr)
    return p.returncode


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="LeadFlow V2 task and evidence state machine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(func=cmd_init)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("prepare").set_defaults(func=cmd_prepare)
    sub.add_parser("verify").set_defaults(func=cmd_verify)
    rv = sub.add_parser("review")
    rv.add_argument("--verdict", required=True)
    rv.add_argument("--notes", default="")
    rv.set_defaults(func=cmd_review)
    sub.add_parser("advance").set_defaults(func=cmd_advance)
    ds = sub.add_parser("review-deepseek")
    ds.add_argument(
        "--round",
        required=True,
        choices=["architecture", "security", "ui", "release", "all"],
    )
    ds.set_defaults(func=cmd_review_deepseek)
    cx = sub.add_parser("codex")
    cx.add_argument("--dry-run", action="store_true")
    cx.set_defaults(func=cmd_codex)
    return ap


def main() -> int:
    args = parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
