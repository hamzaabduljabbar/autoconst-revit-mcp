# Design: `bim_health_audit` / `bim_health_fix` — native BIM Health Scorecard tools

Status: DRAFT for independent review (Codex) · Author: Claude (with Hamza Jabbar) · 2026-10-02

> Reviewer: this doc is self-contained. Please challenge scope, architecture, the
> parity strategy and the safety rules, and answer the **Open questions** at the end.
> Nothing is implemented yet.

---

## 1. Context

**AutoConst Revit MCP** (this repo) is an MCP server for Autodesk Revit. Architecture:

```
MCP client ──stdio──> main.py + tools/*.py   (CPython 3.11+, FastMCP)
                         │ HTTP  localhost:48884/revit_mcp/<route>/
                         ▼
                      revit_mcp/*.py  (pyRevit Routes, IronPython 2.7, runs INSIDE Revit)
                         │
                         ▼
                      Revit API (active document)
```

- Each MCP tool = a thin CPython wrapper in `tools/` + a route in `revit_mcp/` registered in `startup.py`.
- Route handlers run on Revit's thread; writes must use an explicit `DB.Transaction`.
- `tests/test_offline.py` + `tests/tool_contract.json` lock tool names/input schemas.

**Today**, the BIM Health Scorecard is a separate Claude *skill*
(`autoconst-claude-bim-health-scorecard` repo). The skill pastes a 213-line IronPython
script (`engine/score_model.py`) into the generic `execute_revit_code` tool on every run,
writes JSON, then a host-side script (`engine/build_scorecard.py`, openpyxl) builds an Excel
scorecard. A second script (`engine/autofix_assembly_code.py`) fills blank Uniformat codes.

**Problems with the current approach**
1. Depends on the model faithfully re-sending a long script each run — token cost, and a
   risk of the script being altered/truncated between runs (non-repeatable grades).
2. Only works in Claude with the skill installed; not usable from other MCP clients.
3. `execute_revit_code` auto-commits, so the auto-fix has no structured dry-run/confirm step.

## 2. Goal

Ship the scorecard as **first-class MCP tools** so any MCP client gets a repeatable,
structured audit with one call, and the fix is a safe, explicit, two-step operation.

Non-goal: changing *what* the scorecard measures. v1 is a **faithful port** of engine v1.3.

## 3. Scope

### In scope (v1)
| Tool | Purpose |
|---|---|
| `bim_health_audit` | Run all v1.3 rules on the active model; return grade, category scores, per-rule results, failing element IDs (capped). Read-only. |
| `bim_health_fix` | Fill blank Uniformat **Assembly Code** on element **types** (v1.3 auto-fix logic). Dry-run by default. |

Plus a `profile` subset the future `quantity_takeoff` tool can call: `checks="quantity"`
(see §6).

### Out of scope (v1) — stays in the skill or later
- Excel generation (stays host-side in the skill's `build_scorecard.py`; it consumes the tool's JSON).
- Color-splash visualisation (existing `color_splash` tool can be fed the failing IDs).
- UK/Uniclass profile, YAML-driven custom rules (`rules/*.yaml` exist but engine v1.3 hard-codes rules; keep parity first).
- OmniClass fixes (read-only via API; needs family editor — impossible through MCP).
- Linked models (audit the host document only; report link count).

## 4. Tool contracts

### 4.1 `bim_health_audit`
Input:
```json
{
  "stage": "design | fabrication | operations",   // default "design"
  "checks": "all | quantity",                      // default "all"
  "max_failing_ids": 200                           // per rule, default 200
}
```
Output (JSON string via existing `format_response`; numbers below are shape placeholders except `overall`/`grade`, which are the Snowdon baseline):
```json
{
  "status": "success",
  "engine_version": "1.3",
  "model": "Snowdon Towers Sample Architectural",
  "stage": "design",
  "overall": 85.77,
  "grade": "B",
  "category_scores": {"naming": 0, "parameters": 0, "classification": 0, "geometry": 0, "worksharing": 0},
  "rules": [
    {"id": "P-06", "category": "parameters", "name": "Doors: Type Mark/Width/Height",
     "severity": "fail", "weight": 2, "source": "LOD C1030", "advisory": false,
     "pass_rate": 0.93, "element_count": 142, "fail_count": 10,
     "failing": [{"id": 745589, "reason": "Type Mark"}], "failing_truncated": false}
  ],
  "summary": {"rules_run": 0, "rules_failing": 0, "elements_checked": 0},
  "message": "Grade B (85.8/100), stage=design"
}
```
Rule results keep v1.3 field semantics (`passrate`, `fails`, `src`, `na`) renamed to
readable keys; the skill's `build_scorecard.py` gets a small adapter.

### 4.2 `bim_health_fix`
Input:
```json
{ "fix": "assembly_code", "apply": false }
```
- `apply=false` (default): returns per-category targets: `{category, blank_types, fill_value, fill_source: "modal|default"}`. Writes nothing.
- `apply=true`: performs the same plan inside ONE named transaction
  (`"AutoConst: fill Assembly Codes"`), returns filled type IDs. Single Ctrl+Z undoes it.
- Never overwrites a non-empty value. Skips read-only params.

## 5. Architecture / where code lives

| Layer | File | Responsibility |
|---|---|---|
| Revit side | `revit_mcp/health_audit.py` (new) | Rule engine ported from `score_model.py`: collectors, param rules, classification, geometry, naming, worksharing, scoring. Pure functions returning dicts. |
| Revit side | `revit_mcp/health_rules.py` (new) | Rule table (the `PARAM_RULES` list etc.) separated from engine code, so a later YAML loader can replace it. |
| Revit side | routes `/health_audit/` (GET-like POST), `/health_fix/` (POST) registered in `startup.py` | Parse input, call engine, `make_response`. |
| MCP side | `tools/health_tools.py` (new) | `bim_health_audit`, `bim_health_fix` wrappers + docstrings. |
| Tests | `tests/test_offline.py`, `tool_contract.json` | Contract regenerated (+2 tools); offline tests for input validation/formatting. |
| Tests | `tests/live/check_health_audit.py` (new) | Live parity test vs Snowdon baseline (§7). |

**Why the rules run Revit-side, not host-side:** the checks need hundreds of
`LookupParameter` calls on thousands of elements; doing that over HTTP per element would be
orders of magnitude slower. Only the result (scores + capped failing IDs) crosses HTTP.

**IronPython 2.7 constraints:** no f-strings, `unicode` for text, guard `.Name` access,
avoid py3-only syntax. (A stray py3/escape syntax error in one module previously aborted
`startup.py` and silently dropped every later route — so: see Q5.)

## 6. `checks="quantity"` profile (for the future takeoff tool)

Runs only checks that change quantity correctness, all read-only:
- Structural framing/columns missing `Structural Material` (existing P-09/P-09c).
- Rooms unplaced or area ≤ 0 (existing P-11).
- In-place families (existing G-02) — often unmeasurable/mis-categorised.
- Imported CAD (existing G-03).
- **New (not in v1.3, flagged as such):** host elements (walls/floors/roofs/ceilings/columns/framing)
  with **no material** or **zero volume**; elements in **Generic Models**.
The new checks do NOT affect the `checks="all"` grade (parity preserved).

## 7. Parity & test plan

1. **Parity (gate):** on Snowdon Towers Sample Architectural, design stage,
   `bim_health_audit` must reproduce the v1.3 skill result: overall **85.77 → grade B**,
   identical category scores, identical per-rule pass rates and fail counts.
   Baseline: `autoconst-claude-bim-health-scorecard/outputs/scorecard_data.json`
   (2026-07-31). Re-run the v1.3 script live first to confirm the baseline still holds on
   the current Revit install before comparing.
2. **Stage switching:** fabrication stage changes P-09m severity (info→fail); assert the grade moves accordingly.
3. **Fix dry-run:** `apply=false` writes nothing (element count + a sampled Assembly Code unchanged).
4. **Fix apply:** on a scratch copy of the model only (never the shipped sample in Program Files):
   apply → re-audit shows C-04/C-05 pass rates up, then Ctrl+Z restores (single transaction).
5. **Offline:** contract test updated; formatter handles the new payload; input validation (bad stage / checks value → 400).
6. **Skill update:** `bim-health-scorecard` SKILL.md switched to call the tools; Excel builder reads new JSON via adapter; regenerate the Snowdon Excel and diff key cells vs the old one.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Port drifts from v1.3 math | Parity gate in §7.1 before merge. |
| Large models: HTTP timeout | Cap failing IDs; measure runtime on Snowdon (17k elements); route timeout documented. |
| Fix writes to a user's real model | Dry-run default; explicit `apply=true`; one named transaction; never overwrite. |
| One bad module kills all routes at startup | Q5. |
| v1.3 known-questionable logic (below) | Port as-is for parity, list as follow-ups, don't silently "fix". |

**Known questionable v1.3 behaviours (ported as-is, follow-up candidates):**
- Auto-fix fills ALL blank types in a category with that category's single most-common code
  (e.g. every blank framing type gets the same Uniformat code) — plausible for consistency,
  but could be wrong per type.
- Auto-fix comment says doors resolve by Function, but Doors are not in `CATS` → doors never fixed.
- `pget` falls back from instance to type parameter by name; `AsValueString()` is preferred over
  `AsString()` (a fix to prefer `AsString()` was reverted in the skill repo — reason not recorded).
- Thresholds/weights are Tier-3 opinions (see skill repo `VERIFICATION.md`).
- `na_allowed=(STAGE == "design")` is evaluated at import time in v1.3; in a route it must be per-request.

## 9. Open questions for reviewer
1. Should the engine live in one Revit-side module, or split engine/rules as proposed (§5)?
2. Is returning failing IDs capped at 200/rule the right trade-off, or should the tool write
   the full result to a JSON file on disk and return its path?
3. Should `bim_health_fix` be its own tool, or a mode of `bim_health_audit`? (Proposed: separate — read vs write tools should be distinct for client permission prompts.)
4. Parity first, or correct the questionable v1.3 behaviours (§8) in the same change?
5. `startup.py` registers modules sequentially in one try-block; one import error drops every
   later route. Should we harden registration (per-module try/except + logged failure + a
   `/health` route listing which modules loaded) as part of this work or separately?
6. Licensing: the scorecard repo is the author's own (Source-Available license); this MCP repo
   is MIT-derived. Porting the engine into the MCP repo — any license-boundary concern the
   author should decide on before merge?
