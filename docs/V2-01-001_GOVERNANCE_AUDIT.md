# V2-01-001 Governance Audit

Date: 2026-06-16

## Scope

Initialize repository governance, validate installed third-party skills, confirm `.autopilot` persistence policy, and establish the old-project migration matrix before V2 feature implementation begins.

## Skill Source Validation

Third-party skill lock file: `.agents/skill-lock.json`.

| Skill | Repository | Commit pinned | SKILL.md present | Script execution |
|---|---|---:|---|---|
| `ui-ux-pro-max` | `https://github.com/nextlevelbuilder/ui-ux-pro-max-skill.git` | `b7e3af80f6e331f6fb456667b82b12cade7c9d35` | Yes | Not executed |
| `frontend-design` | `https://github.com/anthropics/skills.git` | `57546260929473d4e0d1c1bb75297be2fdfa1949` | Yes | Not executed |
| `web-design-guidelines` | `https://github.com/vercel-labs/agent-skills.git` | `f8a72b9603728bb92a217a879b7e62e43ad76c81` | Yes | Not executed |
| `motion-design` | `https://github.com/LottieFiles/motion-design-skill.git` | `f9a8a041b85185ee4881b3471d3415e939aac772` | Yes | Not executed |

`tools/install_ui_skills.py` clones and copies only the declared skill directory, checks that `SKILL.md` exists, writes the lock file, and prints that no third-party skill scripts were executed. V2-01-001 did not run the installer or any third-party scripts.

## Autopilot Persistence Policy

Persist:

- `.autopilot/state.json`
- `.autopilot/packets/*.md`
- `.autopilot/evidence/*.json` when needed as gate evidence
- `.autopilot/reviews/*.json` when needed as review evidence

Ignore runtime artifacts:

- `.autopilot/logs/`
- `.autopilot/tmp/`
- `.autopilot/screenshots/`
- `.autopilot/controller-output/`

The repository `.gitignore` enforces the runtime artifact exclusions above. Staging must always use explicit file paths, never `git add .` or `git add -A`.

## Old Repository Read-Only Check

Old reference repository: `C:/Users/97020/Desktop/leads-saas`.

Observed `origin/main` HEAD: `c7e77f6` (`Merge pull request #9 from liumingyang-maker/task/P0-007-harden-inbound-api`).

P0 completion evidence is present in old history through:

- P0-000 baseline: `d5f8248`, `a374009`
- P0-001 default admin removal: `9210b95`, `e21306f`
- P0-002 CSRF hardening: `e6d5d26`, `9e911ba`, `1394f4f`, `9c1d28a`
- P0-003 task tenant isolation: `5c0a107`, `deecb37`
- P0-004 signed click redirect: `e63c4c7`
- P0-005 cookie/proxy/account guard: `4375638`
- P0-006 tenant secret encryption: `3a729a0`
- P0-007 inbound hardening: `5d791bb`

The old worktree already contains unrelated local/untracked files. V2 work must not modify, clean, reset, or stage anything in that repository.

## Worker Availability Finding

Reasonix MCP healthcheck currently reports `workspaceRoot` as `C:/Users/97020/Desktop/leads-saas`, the old read-only repository. The controller must not delegate V2 implementation to that MCP target until the worker root is corrected to `C:/Users/97020/Desktop/leadflow-saas-v2`. This is a governance safety finding, not permission to modify the old repository.

## Git Policy

Per updated unattended delivery strategy:

- Milestone branch for V2-01: `milestone/V2-01-foundation`
- V2 currently has no configured remote.
- Remote PR/CI actions are skipped while no remote exists; local commits and local gates continue.
- Production deploy remains forbidden.

## Decision

V2-01-001 may pass once local governance tests, lint/format gates, `git diff --check`, and autopilot review evidence pass.
