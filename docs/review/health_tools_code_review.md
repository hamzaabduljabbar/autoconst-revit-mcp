# Code review brief: `bim_health_audit` / `bim_health_fix`

One round of code review (not design). Please report concrete defects with file:line, a
failure scenario, and severity. Skip style nits. "No findings" is a valid answer.

## What was built
Native MCP tools porting the BIM Health Scorecard engine v1.3 (previously a script pasted into
`execute_revit_code`). Design: `docs/design/bim_health_audit.md` (rev 4, already reviewed in 3 rounds).

Repo: `C:\Users\Hamza\autoconst-revit-mcp` (branch `master`). Commits: `9e7ba74`, `732d0d7`, `05c8766`.

## Files to review
| File | Runs in | What it does |
|---|---|---|
| `startup.py` | Revit (IronPython 2.7) | Registers route modules one by one with per-module try/except; `/routes_status/` lists loaded/failed |
| `revit_mcp/health_rules.py` | Revit | v1.3 rule table (data only) |
| `revit_mcp/health_engine.py` | Revit | Audit scoring + Assembly Code fix plan / plan_id / apply |
| `revit_mcp/health_routes.py` | Revit | `/health_audit/`, `/health_fix/` routes, validation, error codes |
| `tools/health_tools.py` | CPython 3.11 | MCP tool wrappers; whole result is one JSON document; 180 s timeout |
| `tests/test_offline.py` (end) | CPython | Syntax check of Revit-side files; JSON-output test |
| `tests/live/*.py` | CPython | Baseline capture, parity check, baseline comparison |

Related (separate public repo `C:\Users\Hamza\autoconst-claude-bim-health-scorecard`, commits
`65ac62d`, `203a7df`): `engine/build_scorecard.py` (`--fetch`, `normalize()`), `SKILL.md`,
`engine/color_splash_failures.py`.

## Already verified live (Revit 2024, Snowdon Towers Sample Architectural)
- Parity with unmodified v1.3 engine, all three stages: every rule's severity, advisory flag, pass
  rate (|Δ|<1e-9), fail count, failing IDs, category scores, overall, grade. 9–24 s, 81 KB uncapped.
- Fix: preview wrote nothing; apply committed 53 types (design 85.1522 → 85.7689, only the five
  covered C-04 rules changed); reusing the old plan_id → 409 `stale_plan`; one Ctrl+Z → 85.1522 exactly.
- Offline: 24 tests pass; builder `normalize()` checked for complete / capped / over-limit /
  missing-rows / error inputs.

## Please focus on
1. **Parity risks not covered by Snowdon** (no structural framing/columns/foundations, no MEP
   equipment, not workshared): anything in `health_engine.py` that would diverge from v1.3
   `engine/score_model.py` (scorecard repo, commit `c9e9887`) on other models.
2. **Write safety in `apply_fix`**: plan_id composition (`doc.GetHashCode()`, title, path, per-type
   current/proposed), revalidation inside the transaction, rollback paths, and whether every response
   reports the transaction status truthfully (`committed` / `rolled_back` / `unknown`).
3. **IronPython 2.7 / Revit API pitfalls**: `unicode`, `hashlib` fallback, `ElementId` construction
   (2024 vs 2027), `.IntegerValue` vs `.Value`, `request.data` type, `isinstance(cap, int)` for JSON
   numbers (could a client send `200.0`?).
4. **`startup.py`**: can `/routes_status/` itself fail? Is `__import__(..., fromlist=...)` equivalent to
   the old `from x import y` under pyRevit?
5. **Builder `--fetch`**: completeness assertion, SAMPLE labelling, legacy-format compatibility.

## Known and accepted (do not report)
- v1.3 quirks kept for parity: P-09m always advisory; one modal code per category in the fix
  (e.g. faucets/grates get D2010110); Doors and C-05 not fixable; `AsValueString()` preferred.
- No pagination (release 2); quantity-check profile deferred.
- Health tools bypass the shared `format_response` on purpose (single JSON document).
