# P2-5 Radar Release Gate

**Goal:** Record final verification evidence and keep the capability disabled unless the operator explicitly enables it.

**Verified locally:** migration head, focused Radar/Acquisition suites, full non-Browser regression, scoped Ruff, diff check, and Docker Browser-worker isolation smoke.

**Release constraints:**

- COMPETITOR_RADAR_ENABLED remains false by default.
- Radar Runs remain manually requested only; no scheduling control or scheduler is introduced.
- Browser fallback remains disabled unless the existing isolation policy and capability are explicitly approved.
- The remaining release evidence requiring an external labeled corpus/staging sample is not manufactured locally.

**Required operator decision:** approve capability enablement only after reviewing the final audit and after the 50+ labeled-case precision corpus is supplied and replayed.
