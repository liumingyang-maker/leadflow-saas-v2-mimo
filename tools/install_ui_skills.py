from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "skill_sources.json"
DEST = ROOT / ".agents" / "skills"
LOCK = ROOT / ".agents" / "skill-lock.json"


def run(cmd: list[str], cwd: Path | None = None) -> str:
    p = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\n{p.stdout}\n{p.stderr}")
    return p.stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="Install without prompt")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    DEST.mkdir(parents=True, exist_ok=True)
    lock = {"skills": []}

    if not args.yes:
        answer = input(
            "Clone and copy listed third-party skills without executing their scripts? [y/N] "
        )
        if answer.lower() != "y":
            print("Cancelled.")
            return 1

    for item in manifest["skills"]:
        with tempfile.TemporaryDirectory(prefix="leadflow-skill-") as td:
            checkout = Path(td) / "repo"
            run(["git", "clone", "--depth", "1", item["repo"], str(checkout)])
            commit = run(["git", "rev-parse", "HEAD"], cwd=checkout)
            source = checkout / item["path"]
            if not (source / "SKILL.md").exists():
                raise RuntimeError(f"{item['name']}: SKILL.md not found at {source}")
            target = DEST / item["name"]
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)
            lock["skills"].append(
                {
                    "name": item["name"],
                    "repo": item["repo"],
                    "path": item["path"],
                    "commit": commit,
                    "declared_license": item["license"],
                }
            )
            print(f"Installed {item['name']} @ {commit[:12]}")

    LOCK.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    print(f"Wrote {LOCK}")
    print("No third-party skill scripts were executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
