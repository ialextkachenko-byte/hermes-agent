# Hermes Agent Upgrade Plan — `_test-cutover` (97202b86fa) → `origin/main` (f15a38ee, +5136)

**Author:** architect analysis pass (read-only), 2026-08-07 18:08–18:30 MSK
**Repo:** `/home/tkachenkoav/hermes-agent` · **Profile:** `tz-dev`
**Backup:** `~/.hermes/_Archives/hermes-backup-20260807-175807.tar.gz` (340M, verified readable — contains `~/.hermes` runtime state, NOT the git repo)

---

## ⚠️ CRITICAL OPERATIONAL FINDING — read this first

**Another process/session is concurrently operating on this exact branch.** During this
analysis, a `git merge --no-commit --no-ff origin/main` was found *already in progress*
on `_test-cutover` (started ~18:08, `MERGE_HEAD` present, 3 files `UU`: `cron/scheduler.py`,
`gateway/run.py`, `tests/cron/test_scheduler.py`) — identical to the one this task asked
me to run. Mid-analysis, that merge state **disappeared** (`git reflog`: `HEAD@{0}: reset:
moving to HEAD`) — something else ran `git merge --abort` / `git reset --hard` on this
checkout while I was reading it. There is also a **live gateway process** for this profile
(`pid 1623260`, `hermes gateway run`, up since Aug 5) that must not be restarted.

**Do not start the real (non-dry) merge until you've confirmed no other agent/operator is
mid-flight on this same checkout.** Recommend: check with whoever is running the parallel
session, or move the real merge to an isolated `git worktree` so dry-runs and inspection
never collide with someone else's in-progress state again.

---

## 1. Statistics

| Metric | Value |
|---|---|
| Local commits ahead of merge-base | 12 (4 real code changes, 7 pure progress-tracking notes in `.upstream-progress/`, 1 merge commit) |
| Commits behind `origin/main` | 5136 |
| **Commits behind that landed *after* our last validation pass (2026-07-16)** | **4957 of 5136 (96.5%)** |
| Files changed upstream in our declared risk zones | 62 (`cron/` 6, `gateway/` 55, `agent/prompt_builder.py` 1) |
| `gateway/run.py` upstream churn | +37,716 / −17,733 lines (36,958 diff lines) across the 5136-commit span |
| **Real merge conflicts found (`git merge --no-commit --no-ff origin/main`, reproduced twice)** | **3 files**: `cron/scheduler.py`, `gateway/run.py` (3 hunks), `tests/cron/test_scheduler.py` |
| Files in the 62-file risk list that auto-merged cleanly (textually) | 59 |
| Baseline full-suite test run | **In progress in background**, started 18:18 MSK — see §6 |
| Disk free | 178G / 199G — not a constraint |
| `.git` size | 1.7G |

---

## 2. Which of our 12 local commits are already in `origin/main`

None of the 4 real code-change commits are present upstream verbatim, but upstream has
**independently fixed the same bug classes** in 3 of the 4 cases:

| Our commit | Upstream equivalent found? | Verdict |
|---|---|---|
| `276cb5296e` fix(cron): SILENT-guard last-line-equals rule (Variant A) | **Yes — superseded.** `136f8dab67` promoted a strictly broader shared matcher (`gateway.response_filters.is_autonomous_silence_response`), used by `55d3272286`, `f284d85efa`, `5f7deeba84`. Our own commit's in-code comment already documents "*our local Variant-A patch superseded ... dropped in favor of upstream*" from an **earlier** cutover (05.07.2026) — the conflict is just a stale comment block + one dead constant (`_CRON_SILENCE_TOKENS`, unused anywhere) that never got cleaned up. | **Drop ours, take upstream's side verbatim.** |
| `97202b86fa` fix(gateway): retry home-channel startup notification when send-path is still degraded | **No direct equivalent, but adjacent fixes exist**: `476c897439` (`_send_path_degraded` flag + gating, already in our tree since an earlier merge), `2ecb6f7fe6` (clears flag on reconnect), `df2420f571` (byte-identical send shape). Upstream's own retry primitive (`_send_path_degraded` / a polling-progress event) is what our commit *builds on* — but upstream has since routed these two call sites through a **new architecture-level `DeliveryTransport` abstraction** (`gateway/delivery.py`, `resolve_delivery_transport()`) for relay-lane support, which our patch predates. `DeliveryTransport.send()` itself does **not** implement retry-on-degraded — so our fix is **not redundant**, but it targets the wrong layer now (`adapter.send()` directly instead of `transport.send()`). | **Real conflict — must be manually re-targeted (see §4).** |
| `352b040249` feat(gateway): additional startup notification channels for Telegram | No upstream equivalent found (searched for "additional startup channel(s)" in `origin/main` log — no hits). | **Ours, unique — auto-merged cleanly, keep as-is.** Verified: `additional_startup_channels` field and its `TELEGRAM_ADDITIONAL_STARTUP_CHANNELS` env-bridge survive intact post-merge in `gateway/config.py`. |
| `03472b1b33` feat(telegram): opt-in DEBUG logging via `extra.debug` config flag | No upstream equivalent found. | **Ours, unique — auto-merged cleanly, keep as-is.** Verified: `extra.debug` gate survives in `plugins/platforms/telegram/adapter.py` post-merge. |

The other 7 commits (`03f8f5fe24`, `86e2d268b6`, `68b72649c5`, `7e014d4ac9`, `b64168d7d9`,
`6009e1f6a3`, `a3798458a1`) only touch `.upstream-progress/*` tracking files — **zero code
risk**, and `ede3bae5fb` is the merge commit from a *previous* upgrade cycle (see §2.1).

### 2.1 Why "5136 behind" is misleading — this is upgrade cycle #2, not #1

Commit `a3798458a1` ("config migrate 23→33") and the dated `.upstream-progress/step-*`
files show a **prior upgrade pass was already executed and partially validated on
2026-07-15/16** against an older `origin/main`. **4957 of the current 5136 commits landed
after that validation date** — meaning the existing `.upstream-progress/step-3.4-whitelisted.txt`
(30 accepted gateway-test failures) and the cron/config/auxiliary PASS results are
**stale and must not be trusted**. Re-validation from scratch (§6) is mandatory, not optional.

---

## 3. Config.yaml / schema changes

- No root-level `config.yaml` ships in the repo; the schema lives in code
  (`hermes_cli/config.py` + `hermes_cli/config_defaults.py`, refactored out of a single
  file somewhere in the 5136-commit span). `hermes_cli/config.py` shows heavy churn but
  the `_config_version` plumbing (`check_config_version`, `_coerce_config_version`,
  `preserve_keys`) is **identical** between HEAD and `origin/main` — no conflict here, and
  it auto-merged with 0 `UU`.
- **Live finding via `hermes -p tz-dev doctor`:** the `tz-dev` profile's
  `~/.hermes/profiles/tz-dev/config.yaml` (24 lines, override-only) has **no
  `_config_version` key at all** → doctor reports `Config version outdated (v0 → v33)`.
  This contradicts the `a3798458a1` "config migrate 23→33" commit message — that migration
  either targeted a different profile/location or was never persisted for `tz-dev`. Per
  AGENTS.md this is *not* floor-refused (no explicit low version blocking auto-migration),
  but it means **the migration claimed in step 2.5 needs to be re-verified for this profile
  specifically**, not assumed done.
- Doctor also flags: `model.default 'qwen/qwen3.6-plus'` — vendor-prefixed slug on a
  non-aggregator provider (`tutu`) — pre-existing, unrelated to the merge, informational only.

---

## 4. Real conflicts — detail and resolution strategy

### 4.1 `cron/scheduler.py` + `tests/cron/test_scheduler.py` — **LOW risk, trivial**

One conflict hunk each, both are the SILENT-marker note/dead-constant vs. upstream's
shared-matcher comment (see §2 row 1). `tests/cron/test_scheduler.py`'s conflict is 4 of
our old Variant-A-specific test cases (`test_silent_with_note_suppresses_delivery`,
`test_silent_trailing_suppresses_delivery`, `test_silent_is_case_insensitive`,
`test_bracketless_silent_variants_suppress`) vs. upstream simply not having them (upstream's
equivalent coverage lives in `tests/cron/test_cron_silent_marker.py`, which **already exists
in our tree, already tests the surviving `_is_cron_silence_response` function**, and needs
no changes).

**Resolution:** take `origin/main`'s side wholesale for both files.
```bash
git checkout --theirs cron/scheduler.py tests/cron/test_scheduler.py
git add cron/scheduler.py tests/cron/test_scheduler.py
grep -rn "_CRON_SILENCE_TOKENS\|_classify_silent_marker" --include="*.py" .   # must be empty
```
PASS criterion: grep returns nothing; `pytest tests/cron/test_scheduler.py tests/cron/test_cron_silent_marker.py` green.

### 4.2 `gateway/run.py` — **HIGH risk, real architectural conflict, 3 hunks**

Our `97202b86fa` added `_send_with_polling_settle()` — a wrapper that retries
`adapter.send()` once after waiting for `_polling_progress_event` when
`_send_path_degraded` is set — and called it from two sites: the restart notification and
the home-channel startup notification.

Upstream, in the same window, introduced `gateway/delivery.py`
(`DeliveryTransport` dataclass + `resolve_delivery_transport()`) and rewired **those same
two call sites** to go through `transport.send(...)` instead of `adapter.send(...)`
directly, so relay-fronted platforms (not just native adapters) can serve as the home
channel. `DeliveryTransport.send()` itself does no retry — it just dispatches to
`adapter.send_for_platform()` (relay) or `adapter.send()` (native).

**These are not redundant — they solve different problems and both must survive.** The fix
is architectural, not a pick-one-side conflict:

- Keep upstream's `resolve_delivery_transport()` / relay-metadata / byte-identical-send logic in full (all 3 conflict hunks' `origin/main` side).
- Re-point `_send_with_polling_settle()` to operate on the **native-adapter case only**
  (`transport.adapter.send(...)`, gated on `not transport.is_relay` — relay lanes have no
  `_send_path_degraded` concept), OR — cleaner, and preferred per "extend existing code"
  (Footprint Ladder rung 1) — push the retry into `DeliveryTransport.send()` in
  `gateway/delivery.py` itself, guarded by `getattr(self.adapter, "_send_path_degraded", False)`,
  so every current and future caller of `transport.send()` benefits uniformly, not just
  these two call sites.
- The **recommended** shape: move `_send_with_polling_settle` (or an equivalent) into
  `gateway/delivery.py` as `DeliveryTransport._send_with_settle()`, called from
  `DeliveryTransport.send()` for the non-relay branch only. Delete the now-unneeded
  standalone `_send_with_polling_settle` from `gateway/run.py` and update its two call
  sites to just call `transport.send(...)`.

**This is a real code-writing task, not something to resolve blindly with `--ours`/`--theirs`.**
Budget real engineering time for it — do not attempt this unattended.

PASS criterion:
1. `tests/gateway/test_telegram_startup_notification_retry.py` (our existing 158-line test file) still passes, extended with a case asserting the relay-transport path does **not** attempt the retry/settle wait (relay adapters don't have `_send_path_degraded`).
2. `pytest tests/gateway/ -k "startup_notification or delivery or restart"` green.
3. Full `tests/gateway/` suite (§6) shows no *new* regressions vs. baseline.

### 4.3 Everything else in the 62-file risk list (59 files) — auto-merges cleanly

Verified via the dry-run: `agent/prompt_builder.py`, `cron/jobs.py`, `cron/executions.py`,
`cron/lifecycle_guard.py`, `cron/scheduler_provider.py`, `cron/suggestions.py`,
`gateway/config.py`, and 52 other `gateway/*` files all merge with **zero conflict markers**.
"Clean" here means *textual* 3-way merge success only — semantic correctness for a file
like `gateway/run.py` (36,958 diff lines total, of which only ~40 lines are the 3 conflicted
hunks) is **not proven by the absence of markers** and must be established by the test
suite in §6, especially since upstream added entirely new subsystems in this window
(`gateway/turn_lease.py`, `gateway/session_state.py`, `gateway/shutdown_watchdog.py`,
`gateway/lifecycle_ledger.py`, `gateway/relay/*` expansion) that our surviving local code
(profile routing, multi-channel startup notifications) has never been tested against.

---

## 5. Step-by-step plan

Legend: **Risk** = low/medium/high. Every step has an explicit PASS/FAIL gate; do not
proceed past a FAIL without human sign-off.

### Step 0 — Pre-flight (Risk: low)
```bash
cd /home/tkachenkoav/hermes-agent
git status --porcelain=v1 | grep -E '^(UU|AA|DD)'   # must be EMPTY (confirms no leftover merge)
ls .git/MERGE_HEAD 2>&1                               # must say "No such file or directory"
git log -1 --oneline                                  # must be 97202b86fa
tar -tzf ~/.hermes/_Archives/hermes-backup-20260807-175807.tar.gz > /dev/null   # exit 0
ps aux | grep "hermes_cli.main gateway run" | grep -v grep   # confirm still running, note PID, DO NOT TOUCH
```
**PASS:** all four checks pass. **FAIL:** stop, do not proceed — someone else is mid-operation.

### Step 1 — Coordinate exclusivity (Risk: medium — process risk, not code risk)
Confirm with whoever else may be running the parallel session (see the critical finding
above) that no one else will touch `_test-cutover` for the duration of Steps 2–9. Optionally
do the real work in `git worktree add ../hermes-agent-upgrade _test-cutover` instead of the
primary checkout, so the live gateway's working tree (if it reads from this checkout) is
never disturbed mid-merge.
**PASS:** explicit go-ahead obtained, or isolated worktree created.

### Step 2 — Baseline tests (Risk: low) — **already started**
```bash
scripts/run_tests.sh -q 2>&1 | tee /tmp/baseline_run_tests_sh.log | tail -5
```
Kicked off in background at 18:18 MSK (PID 1713614/1713616), log at
`/tmp/baseline_run_tests_sh.log`. At 8.1% (3127/~38744 tests) the only failures are 3
**pre-existing, unrelated** `tests/acp/test_auth.py` failures plus 9 collection errors —
all caused by a missing `acp` package in `.venv` (`ModuleNotFoundError: No module named 'acp'`).
This is an environment gap, not an upgrade regression — confirm count is stable, then treat
those specific tests as pre-red baseline (exclude from regression comparison) or fix the
venv (`pip install` the ACP SDK) before finalizing baseline.
**PASS:** run completes; note final pass/fail/error counts as the reference baseline.
**Check progress:** `tail -20 /tmp/baseline_run_tests_sh.log`

### Step 3 — Reproduce the dry-run merge (Risk: low, already done twice, deterministic)
```bash
git merge --no-commit --no-ff origin/main
git diff --name-only --diff-filter=U
```
**PASS:** exactly 3 files listed: `cron/scheduler.py`, `gateway/run.py`, `tests/cron/test_scheduler.py`.
**FAIL:** any other file appears → upstream moved again since this analysis; re-run full
analysis before continuing. `git merge --abort` immediately if so.

### Step 4 — Resolve the trivial cron conflict (Risk: low)
```bash
git checkout --theirs cron/scheduler.py tests/cron/test_scheduler.py
grep -rn "_CRON_SILENCE_TOKENS\|_classify_silent_marker" --include="*.py" .
git add cron/scheduler.py tests/cron/test_scheduler.py
scripts/run_tests.sh tests/cron/test_scheduler.py tests/cron/test_cron_silent_marker.py -q
```
**PASS:** grep empty, tests green. **FAIL:** stop, do not force-add; inspect manually.

### Step 5 — Resolve `gateway/run.py` (Risk: high — real engineering, not scripted)
Per §4.2: implement the `DeliveryTransport`-level (or transport-gated) retry. This is a
**separate, focused editing task** — do not attempt inline as part of a scripted merge.
Concretely:
1. Accept `origin/main`'s side for the transport-resolution/metadata hunks.
2. Add the degraded-retry wait into `gateway/delivery.py::DeliveryTransport.send()`
   (or a private helper it calls), gated to the non-relay branch.
3. Remove the now-dead standalone `_send_with_polling_settle` from `gateway/run.py`;
   update its 2 former call sites to call `transport.send(...)` plainly.
4. Extend `tests/gateway/test_telegram_startup_notification_retry.py` with a relay-path
   negative case.
```bash
git add gateway/run.py gateway/delivery.py tests/gateway/test_telegram_startup_notification_retry.py
scripts/run_tests.sh tests/gateway/test_telegram_startup_notification_retry.py -q
scripts/run_tests.sh tests/gateway/ -q 2>&1 | tail -20
```
**PASS:** targeted test green; full `tests/gateway/` failure count ≤ baseline (Step 2) count
for pre-existing failures, with zero *new* failures unexplained by a known upstream
regression (re-verify each against a clean `origin/main` checkout in a scratch worktree,
same method as the July whitelist used — do not reuse the July whitelist itself).
**FAIL:** any new failure not traceable to a confirmed upstream-only regression → do not
proceed, revert this file (`git checkout --merge gateway/run.py` to reset to conflict
markers, or `git merge --abort` to restart entirely) and re-design the resolution.

### Step 6 — Confirm zero conflicts remain (Risk: low)
```bash
git diff --name-only --diff-filter=U   # must be empty
```
**PASS:** empty output.

### Step 7 — Full-suite validation (Risk: medium)
```bash
scripts/run_tests.sh -q 2>&1 | tee /tmp/postmerge_run_tests_sh.log | tail -20
diff <(grep -oP '^\S+ \K\S+(?= ::|$)' /tmp/baseline_run_tests_sh.log) \
     <(grep -oP '^\S+ \K\S+(?= ::|$)' /tmp/postmerge_run_tests_sh.log)   # sanity diff, adjust to actual log format
```
**PASS:** post-merge failing set ⊆ (baseline failing set ∪ confirmed-upstream-regressions-verified-fresh-not-from-July-whitelist).
**FAIL:** any unexplained new failure → treat as blocking, do not commit the merge.

### Step 8 — Manual smoke checks (Risk: low)
```bash
hermes -p tz-dev doctor
hermes -p tz-dev status
hermes -p tz-dev config get model.default
hermes -p tz-dev cron list
hermes -p tz-dev tools list
```
**PASS:** doctor shows no NEW red items beyond the pre-existing ones already logged in §3
(config v0→v33, missing OAuth logins, missing docker/Playwright — all pre-existing);
`cron list` and `tools list` run without traceback. **Do not run anything that restarts the
gateway** (`hermes gateway restart`, `hermes serve`, etc. are out of scope for this pass).

### Step 9 — Commit the merge (Risk: medium — first real state change)
```bash
git commit --no-edit   # or a custom message documenting the gateway/run.py reconciliation
git log --oneline -3
git diff HEAD~1..HEAD --stat | tail -5   # sanity: no unexpected deletions (per AGENTS.md stale-branch pitfall)
```
**PASS:** commit succeeds, `--stat` shows the expected shape (net additions across gateway/,
no surprise deletions of files we didn't intend to touch).
**Do not `git push`** — leave the merge commit local for a separate, explicit review/push
decision outside this task's scope.

### Step 10 — Re-run the config-version check for `tz-dev` specifically (Risk: low)
```bash
hermes -p tz-dev doctor | grep -i "config version"
```
If still `v0 → v33`, this is pre-existing (not caused by the merge) — file as a **separate**
follow-up: either run the profile's config through the migration path deliberately
(`hermes -p tz-dev config` triggers the wizard/prompt) or confirm v0 (unversioned override
file) is an accepted steady state for this profile. Out of scope to fix inline here.

---

## 6. Baseline (Step 2 status at time of writing)

- **Command:** `scripts/run_tests.sh -q` (background, started 18:18 MSK)
- **Progress at last check:** 8.1% (3127/~38744 tests), `-j 8`
- **Failures so far:** 3, all `tests/acp/test_auth.py::TestBuildAuthMethods::*` — pre-existing,
  caused by missing `acp` package in `.venv` (also causes 9 file-level collection ERRORs
  in `tests/acp*`, `tests/acp_adapter/*`) — **not related to the upgrade**.
- **Note:** a naive `python -m pytest -q` (as literally suggested) is **not usable** for this
  repo — it aborted after 116s with `Interrupted: 9 errors during collection` because bare
  pytest halts the whole run on any collection error, unlike `scripts/run_tests.sh`'s
  per-file subprocess isolation. Always use the wrapper (AGENTS.md is explicit about this).
- **To check current status:** `tail -30 /tmp/baseline_run_tests_sh.log`
- **Full log:** `/tmp/baseline_run_tests_sh.log`

---

## 7. Strategy recommendation: **merge, not rebase, not squash**

- **Merge** (what this plan does) preserves the 12 local commits' identity. The tooling
  itself depends on this: `hermes --version` reports `local 97202b86 (+12 carried commits)`
  — commit-hash tracking is a first-class concept here, not incidental.
- **Rebase** would rewrite all 12 hashes referenced by the `.upstream-progress/` notes and
  by the very `hermes --version` banner, and — given the confirmed concurrent access to
  this branch (§ critical finding) — replaying commits one-by-one onto a moving target
  while another process might reset/checkout the same ref is materially more dangerous
  than one atomic merge commit.
- **Squash** would discard the fix/feature commit boundaries the team is clearly tracking
  deliberately (`276cb5296e`, `03472b1b33`, `352b040249`, `97202b86fa` each stand alone).
- Precedent: `ede3bae5fb` — the prior upgrade cycle already used a merge commit for exactly
  this operation. Stay consistent.

---

## 8. Rollback plan

| Scenario | Action |
|---|---|
| Dry-run merge (`--no-commit`) misbehaves, want out immediately | `git merge --abort` (verified working, idempotent, already exercised twice in this analysis) |
| Merge committed (Step 9) but tests/smoke fail afterward, not yet pushed | `git reset --hard 97202b86fa` — safe, nothing was pushed, restores the exact pre-merge tip |
| Runtime config/state corrupted by a config-version write during smoke testing | Restore from `~/.hermes/_Archives/hermes-backup-20260807-175807.tar.gz`: extract to a scratch dir (`tar -xzf ... -C /tmp/restore`), **diff before overwriting** — do not blind-copy over a live profile while the gateway process (pid 1623260) is running; this requires a gateway-stop step that is explicitly out of scope for this pass and needs separate sign-off |
| Need to compare against pristine upstream without touching this checkout again | Use a scratch worktree: `git worktree add /tmp/hermes-upstream-check origin/main` (same pattern already used for the July whitelist verification per `.upstream-progress/step-3.4-whitelisted.txt`) |

---

## 9. Open items for a human decision before executing Steps 5–9

1. Who else is operating on `_test-cutover` right now (§ critical finding) — must be resolved before Step 1.
2. Design sign-off on the `DeliveryTransport`-level retry placement (§4.2) — this is new
   production code, not a mechanical conflict resolution.
3. Whether the stale July whitelist (30 gateway failures) should be discarded entirely
   (recommended) or used as a starting hint while re-deriving a fresh one — recommend
   discarding given 96.5% of the commit gap postdates it.
4. Whether to address the `tz-dev` config `v0 → v33` gap as part of this upgrade or file separately.
