# Design: `bim_health_audit` / `bim_health_fix` — native BIM Health Scorecard tools

Status: **REVISION 3** — addresses independent review rounds 1 and 2 (Codex) · 2026-10-02
Author: Claude (with Hamza Jabbar)

> Reviewer: this doc is self-contained. §0 maps each finding to its resolution
> (round 2 first). Nothing is implemented yet. Licensing decided (§11).

---

## 0a. Round-2 review resolutions

| # | Finding | Resolution | Section |
|---|---|---|---|
| R2-1 | Unmodified v1.3 only prints rounded output; can't support 1e-9 parity | Pinned capture script `tests/live/capture_v13_baseline.py`: executes the **unmodified** engine source text (fetched at a recorded scorecard-repo commit) with only `STAGE` substituted and the trailing print block stripped, then serializes in-memory `RESULTS`, `cat_scores`, `overall` at full precision (`repr` floats). Script + engine commit SHA + script SHA-256 recorded in each baseline file. | §7.1 |
| R2-2 | N-01 can log two findings for one family | `fail_count_source: "findings"` for N-01 (and any rule whose v1.3 fails list can hold >1 entry per element). `fail_count` = v1.3 finding count, never deduplicated; `pass_rate` computed exactly as v1.3. Added `distinct_failing_elements` for every element-based rule. | §4.1 |
| R2-3 | Capped response silently truncates the Excel Failing Elements sheet | Product choice: **the Excel is complete.** The skill calls the audit with `max_failing_ids: 0` (= no cap). The builder refuses to write a "complete" sheet if any rule has `failing_truncated: true`; if a cap was used it labels the sheet "SAMPLE — capped" and shows per-rule full and omitted counts. Default cap (200) remains for interactive/chat use. | §3, §4.1, §7.7 |
| R2-4 | "First `{`" parser fragile | Health tools return **one JSON document as the entire text result** (no leading message line; summary lives in `message`). Adapter parses the whole text with `json.loads`. Applies to errors too. | §4.3 |
| R2-5 | Ambiguous commit outcomes | Apply returns `transaction: {status: committed | rolled_back | unknown}` from Revit's `TransactionStatus`, never assumed. "Nothing written" only claimed when rollback is confirmed. Client timeout ⇒ outcome unknown ⇒ re-run preview/audit before any retry; documented in the tool description. | §4.2 |

## 0. Round-1 review resolutions

| # | Finding | Resolution | Section |
|---|---|---|---|
| F1 | Apply can write a different plan than previewed | Dry-run returns a `plan_id` bound to document identity + per-type current/proposed values; apply requires it and revalidates before opening the transaction; stale → reject. Per-type changes and skip reasons returned. | §4.2 |
| F2 | Fix test promised C-05 improvement (impossible) | Fix scope = v1.3 `CATS` (loadable categories only). Test asserts improvement only for affected C-04 rules; C-05 must be **unchanged**. | §4.2, §7 |
| F3 | P-09m stage test contradicts v1.3 logic | Parity release preserves v1.3: `na_allowed` forces `info` before stage lookup, so fabrication does **not** change P-09m. Stage correction deferred to a versioned rule change (engine 1.4) with new expected scores. Absent-category denominator rule defined. | §5.3, §9 |
| F4 | Output contract not lossless | `fail_count` computed before truncation; added `failing_returned`, `failing_truncated`, `fail_count_source`; G-03 special case defined; `elements_checked` defined; adapter parses the real MCP text response. | §4.1 |
| F5 | Quantity profile too broad | Removed from this release. Moved to a separate future design with its own contract. | §3 |
| F6 | Parity needs more than one score | Structured per-rule baseline with full provenance + second small fixture. | §7 |
| Q1 | Split engine/rules | Accepted; doc + stage passed explicitly, no module-level state. | §5 |
| Q2 | Capped IDs, no server file path | Accepted. | §4.1 |
| Q3 | Separate fix tool | Accepted. | §4.2 |
| Q4 | Parity first, versioned correction later | Accepted; write-safety protocol correct from day one. | §5.3, §9 |
| Q5 | Harden route registration | Accepted, in scope as step 0. | §6 |
| Q6 | Licensing | Decision required from author before merge. | §11 |

---

## 1. Context

**AutoConst Revit MCP** (this repo) is an MCP server for Autodesk Revit:

```
MCP client ──stdio──> main.py + tools/*.py   (CPython 3.11+, FastMCP)
                         │ HTTP  localhost:48884/revit_mcp/<route>/
                         ▼
                      revit_mcp/*.py  (pyRevit Routes, IronPython 2.7, runs INSIDE Revit)
                         ▼
                      Revit API (active document)
```

- Each MCP tool = CPython wrapper in `tools/` + a route in `revit_mcp/`, registered in `startup.py`.
- `tests/test_offline.py` + `tests/tool_contract.json` lock tool names/input schemas.
- `tools/utils.py::format_response` returns, on success, either a leading `message` line
  followed by pretty JSON, or pretty JSON alone. Consumers must parse that real text (§4.3).

**Today** the BIM Health Scorecard is a separate Claude skill
(`autoconst-claude-bim-health-scorecard`, engine v1.3). Each run pastes the 213-line
IronPython `engine/score_model.py` into the generic `execute_revit_code` tool, writes JSON,
and a host script (`engine/build_scorecard.py`, openpyxl) builds the Excel. A second script
(`engine/autofix_assembly_code.py`) fills blank Uniformat codes and auto-commits.

**Problems:** token cost and non-repeatability (script re-sent each run), skill-only (other
MCP clients can't use it), and the fix has no real preview/confirm step.

## 2. Goal

First-class MCP tools: a repeatable read-only audit in one call, and a fix whose preview is
exactly what gets applied. **Release 1 is a faithful port of engine v1.3 math**; corrections
come later as versioned rule changes (§9).

## 3. Scope

### In scope (release 1)
0. Harden route registration in `startup.py` (§6) — prerequisite.
1. `bim_health_audit` — read-only, full v1.3 ruleset.
2. `bim_health_fix` — Assembly Code fill, v1.3 fill policy, new plan-bound safety protocol.
3. Skill update: SKILL.md calls the tools; `build_scorecard.py` gets an adapter.

### Out of scope (release 1)
- **`checks="quantity"` profile** — removed (F5). Will get its own design (eligible
  categories, exclusions, units, "quantity risk" vs "confirmed error", findings without a grade)
  alongside the `quantity_takeoff` design.
- Engine 1.4 corrections (§9), Excel generation inside the server, colour-splash, UK/Uniclass
  profile, YAML rule loading, OmniClass fixes (read-only via API), linked models.

## 4. Tool contracts

### 4.1 `bim_health_audit` (read-only)

Input:
```json
{ "stage": "design", "max_failing_ids": 200 }
```
- `stage` ∈ `design | fabrication | operations` (default `design`); anything else → HTTP 400.
- `max_failing_ids` integer ≥ 0 (default 200), per rule. **`0` = no cap** (used by the Excel
  builder, §4.3/§7.7). Counts and scores always reflect the full audit regardless of the cap.

Output (`status: success`):
```json
{
  "status": "success",
  "engine_version": "1.3",
  "ruleset_version": "1.3",
  "document": {"title": "...", "path": "...", "is_workshared": false},
  "stage": "design",
  "overall": 85.77, "grade": "B",
  "category_scores": {"parameters": 0.0},
  "categories_scored": ["parameters", "classification", "geometry", "naming"],
  "categories_not_scored": [{"category": "worksharing", "reason": "only info-severity rules"}],
  "rules": [{
    "id": "P-06", "category": "parameters", "name": "Doors: Type Mark/Width/Height",
    "severity": "fail", "weight": 2, "source": "LOD C1030", "advisory": false,
    "applicable": true,
    "element_count": 142,
    "pass_rate": 0.93,
    "fail_count": 10, "fail_count_source": "elements", "distinct_failing_elements": 10,
    "failing": [{"id": 745589, "reason": "Type Mark"}],
    "failing_returned": 1, "failing_truncated": false
  }],
  "summary": {"rules_run": 0, "rules_scored": 0, "rules_with_failures": 0,
              "unique_elements_checked": 0},
  "message": "Grade B (85.8/100), stage=design"
}
```
Numbers are shape placeholders except `overall`/`grade` (Snowdon baseline).

**Field semantics (lossless):**
- `fail_count` is computed on the **full** result before truncation. `failing` holds the first
  `max_failing_ids` entries in ascending element-ID order (stable). `failing_returned = len(failing)`;
  `failing_truncated = fail_count > failing_returned`.
- `reason`: comma-joined missing parameter names for parameter rules; fixed tokens otherwise
  (`no OmniClass`, `no Assembly Code`, `unplaced/area0`, `unnamed`, `dup`, `illegal`).
- `fail_count_source`:
  - `"elements"` — `fail_count` = number of failing elements; one finding per element.
  - `"findings"` — `fail_count` = number of v1.3 findings, which may exceed distinct elements
    (**N-01**: one family can log both `illegal` and `dup`). Never deduplicated; `pass_rate` is
    v1.3's own value. `failing` lists findings (an element ID may repeat with different reasons).
  - `"aggregate"` — the rule scores a model-level quantity, not elements. Applies to
    **G-01** (Revit warnings: `fail_count` = warning count, `failing = []`, `element_count = null`)
    and **G-03** (imported CAD: v1.3 reports pass rate 0 with an empty fails list;
    release 1 sets `fail_count` = number of non-linked `ImportInstance`s and returns their IDs,
    leaving `pass_rate` exactly as v1.3 computes it).
- `distinct_failing_elements` = number of unique element IDs among findings (null for aggregate rules).
- `applicable: false` when the rule's category has no elements in the model (v1.3 skips the rule
  entirely; release 1 still lists it, with `pass_rate = null`, so absence is visible but scoring is unchanged).
- `advisory` = v1.3 `na` flag.
- `summary.unique_elements_checked` = count of distinct element IDs examined by element-level rules
  (an element checked by three rules counts once).

### 4.2 `bim_health_fix` (writes) — plan-bound two-step

**Step 1 — preview** (`apply` omitted/false):
```json
{ "fix": "assembly_code" }
```
Returns:
```json
{
  "status": "success", "mode": "preview",
  "plan_id": "sha256:…",
  "document": {"title": "...", "path": "..."},
  "changes": [
    {"type_id": 123, "category": "Structural Framing", "type_name": "W12x26",
     "current": "", "proposed": "B1010", "fill_source": "modal"}
  ],
  "skipped": [
    {"type_id": 456, "category": "Windows", "reason": "already_set", "current": "B2020"},
    {"type_id": 789, "category": "Furniture", "reason": "param_read_only"}
  ],
  "summary": {"to_change": 0, "skipped": 0, "categories": []}
}
```
**Step 2 — apply:**
```json
{ "fix": "assembly_code", "apply": true, "plan_id": "sha256:…" }
```

**Plan identity:** `plan_id` = SHA-256 over a canonical JSON of: fix name, ruleset version,
document identity (`doc.Title`, `doc.PathName`, and `doc.GetHashCode()` of the live document object),
and the sorted list of `(type_id, current_value, proposed_value)` for every change.
The server is stateless: apply **recomputes the plan from the live document** and compares hashes.

**Apply algorithm:**
1. `plan_id` missing → 400 (`apply` without a preview is impossible).
2. Recompute plan → hash. Mismatch → 409 `stale_plan` with the fresh preview in the body;
   nothing written. (Covers document switch, intervening edits, changed modal values.)
3. Open ONE transaction `"AutoConst: fill Assembly Codes"`; for each change re-read the param:
   if no longer empty or read-only → roll back the whole transaction, 409 `stale_plan`.
4. Set values; commit. On exception → roll back; respond 500 with traceback.
5. Response always includes `transaction: {"status": "committed" | "rolled_back" | "unknown", "revit_status": "<TransactionStatus>"}`,
   read from the value returned by `Commit()` / `RollBack()` — never assumed. "Nothing written" is
   claimed **only** when status is `rolled_back` (confirmed). Committed → per-type results;
   one Ctrl+Z reverts the whole fix.
6. **Ambiguous outcome:** if the client times out or the connection drops, the outcome is unknown —
   Revit may have committed. A retried apply would then correctly return `stale_plan`. The tool
   description instructs clients: after a timeout, run a fresh preview (or audit) to see the actual
   state before any retry. Never re-apply blind.

**Fill policy (v1.3, unchanged):** categories = v1.3 `CATS` (Structural Framing, Structural
Columns, Structural Foundations, Windows, Plumbing Fixtures, Lighting Fixtures, Casework,
Furniture). Fill value = that category's modal existing code, else the v1.3 Uniformat default.
Never overwrites. **Walls/Floors/Roofs/Ceilings (C-05) and Doors are not touched** — known
gaps, listed in §9.

### 4.3 Response transport & the Excel adapter
The health tools do **not** use the shared `format_response` text layout. Their entire text
result is **one JSON document** (success and error alike; human summary in `message`, errors in
`error`). The skill adapter does `json.loads(text)` on the whole result — no brace scanning.
Tested against a captured real tool response (fixture), not a hand-written dict.

**Excel completeness (product choice):** the scorecard workbook's Failing Elements sheet must be
complete. The skill calls `bim_health_audit` with `max_failing_ids: 0`. The builder checks every
rule's `failing_truncated`; if any is true it titles the sheet **"SAMPLE — capped"** and adds
per-rule `fail_count` and omitted-count columns, so a truncated sheet can never look complete.

## 5. Architecture

### 5.1 Files
| Layer | File | Responsibility |
|---|---|---|
| Revit | `revit_mcp/health_rules.py` | Rule table only (data): param rules, classification category lists, thresholds, weights, grade bands. `RULESET_VERSION = "1.3"`. |
| Revit | `revit_mcp/health_engine.py` | Scoring core: `run_audit(doc, stage, max_ids)`, `build_fix_plan(doc)`, `apply_fix_plan(doc, plan_id)`. **No module-level doc/stage/state**; everything passed in. |
| Revit | `revit_mcp/health_routes.py` | Route adapter: `/health_audit/`, `/health_fix/` (POST); input validation; `make_response`. |
| MCP | `tools/health_tools.py` | `bim_health_audit`, `bim_health_fix` wrappers + docstrings telling clients to preview first. |
| Tests | `tests/test_offline.py`, `tool_contract.json` | Contract +2 tools; offline validation/formatting tests. |
| Tests | `tests/live/check_health_audit.py`, `tests/live/baselines/*.json` | Live parity + fixture tests (§7). |

Rules run Revit-side: thousands of parameter lookups must not cross HTTP per element.

### 5.2 IronPython 2.7 constraints
No f-strings or py3-only syntax; `unicode` for text; guard `.Name`. Verify `hashlib.sha256`
is available in pyRevit's IronPython; fallback: .NET `System.Security.Cryptography.SHA256`. All files must pass a CPython `ast.parse` check in CI
(the escaping bug that previously aborted startup would have been caught).

### 5.3 v1.3 scoring semantics preserved exactly
- `SEV_FACTOR = {fail: 1.0, warn: 0.5, info: 0.0}`.
- Severity resolution per v1.3 `param_rule`: **if `na_allowed` → `info`**, else
  `severity_by_stage[stage]` if present, else `severity`. (P-09m is therefore `info` at every stage.)
- v1.3 quirk preserved: P-04h/p/l set `na_allowed = (STAGE == "design")` — in release 1 this is
  evaluated **per request** from the `stage` argument (behaviour identical to v1.3 when run with that stage; no import-time globals).
- Category score = `100 * Σ(w·sev·pass) / Σ(w·sev)` over rules with `sev > 0` **that ran**.
- **Absent categories / denominator:** a category with zero scoring rules (all skipped because their
  element categories are empty, or all `info`) is **omitted** from `category_scores`, and the overall
  score is the weighted mean over **present** categories only: `Σ(W_c·S_c) / Σ(W_c)` for scored `c`.
  This is v1.3 behaviour; it is made explicit via `categories_not_scored`.
- Grade bands A≥90, B≥80, C≥70, D≥60, else F.

## 6. Step 0 — harden route registration
- `startup.py`: register each module in its own `try/except`; log the traceback via pyRevit logger;
  continue with the next module.
- Keep a module-level `REGISTRY = {"loaded": [...], "failed": [{"module", "error"}]}`.
- New route `/routes_status/` registered **first**, before any feature module, with no imports beyond
  `routes`/`json`, returning `REGISTRY` — so it survives any later failure.
- MCP side: extend `get_revit_status` output with loaded/failed module counts (no new tool, so the
  contract is unchanged apart from the description).
- Offline test: `ast.parse` every `revit_mcp/*.py` and `startup.py`.

## 7. Test plan

**7.1 Baseline capture (before porting).** The unmodified v1.3 engine only prints rounded text,
so a pinned capture script `tests/live/capture_v13_baseline.py` (host side) does:
1. Read `engine/score_model.py` from the scorecard repo at a recorded commit SHA.
2. Make exactly two textual changes: set `STAGE = "<stage>"`, and strip everything from the
   final `print("=" * 66)` block onward (asserting that block is found exactly once).
3. Append a serializer that emits `RESULTS`, `cat_scores`, `overall` as JSON with floats via `repr`
   (full precision), plus each rule's fails list.
4. Send via `execute_revit_code`; write `tests/live/baselines/<model>__<stage>.json`.
Each baseline records the engine commit SHA and the SHA-256 of the capture script. Save a
structured baseline JSON per stage containing:
`{model_title, model_path, file_size, file_mtime, revit_version_build, engine_commit (scorecard repo SHA), stage, overall, grade, category_scores, rules:[{id, severity, advisory, applicable, pass_rate, fail_count}]}`
for each stage (design / fabrication / operations). Compare to the 2026-07-31 saved result (85.77, B)
and record any drift before proceeding.

**7.2 Parity gate (Snowdon Towers Sample Architectural).** For each stage, `bim_health_audit` must
match the baseline on: rule presence, severity, advisory, applicability, pass rate (|Δ| < 1e-9),
fail count, every category score, overall (|Δ| < 1e-9), grade. G-03 `fail_count` is the one
deliberately new field (v1.3 had none) and is checked against a direct `ImportInstance` count.

**7.3 Second fixture (small scratch model)** created by the test via MCP tools into a temp `.rvt`
(never the shipped sample in Program Files). Must cover:
empty categories (rule `applicable: false`, category omitted from denominator);
type-level vs instance-level parameter reads (`pget` instance→type fallback);
duplicate/unnamed levels; a non-workshared doc (W-01 info). Worksharing-enabled coverage is a
known gap unless a workshared fixture can be produced — recorded, not silently skipped.
Expected values are computed by running v1.3 on the same fixture.

**7.4 Stage behaviour (parity):** fabrication and operations results equal their v1.3 baselines;
explicitly assert P-09m is `info` at all stages (documents the quirk).

**7.5 Fix safety** (fixture model only):
- Preview writes nothing (re-audit identical; sampled type values unchanged).
- Apply with matching `plan_id` → C-04 pass rates for affected categories rise to the expected
  value; **C-05 unchanged**; one Ctrl+Z restores the pre-fix audit exactly.
- Apply with a stale plan (edit one type's code between preview and apply) → 409, nothing written.
- Apply after switching active document → 409.
- Apply without `plan_id` → 400.

**7.6 Offline:** contract (+2 tools), input validation (bad stage, bad `max_failing_ids`, apply without plan),
formatter output parsed by the adapter from a captured real response.

**7.7 Skill:** SKILL.md uses the tools; regenerate the Snowdon Excel; key cells match the old
workbook (overall, grade, per-rule pass rates) **and** the Failing Elements sheet row count equals
Σ `fail_count` over rules with element/finding lists (complete, uncapped). A second run with a
small cap must produce the "SAMPLE — capped" title and correct omitted counts.

## 8. Risks
| Risk | Mitigation |
|---|---|
| Port drifts from v1.3 | Structured multi-stage parity gate (§7.2) + second fixture. |
| Large model HTTP timeout | IDs capped; measure Snowdon (17k elements) runtime; document limit. |
| Fix writes something not previewed | Plan-bound apply, revalidation, single transaction (§4.2). |
| One bad module drops all routes | Step 0 (§6) + `ast.parse` CI check. |
| `doc.GetHashCode()` not stable enough as identity | It only needs to distinguish documents within one Revit session between preview and apply; plus title/path and per-type values in the hash. Verify live. |

## 9. Known v1.3 defects — ported as-is, fixed in engine 1.4 (separate versioned change)
1. P-09m stage severity never applies (na_allowed short-circuit).
2. Fill policy assigns one modal code to every blank type in a category.
3. Doors excluded from the fix despite the comment saying they resolve by Function.
4. C-05 (system families) has no fix path.
5. `pget` prefers `AsValueString()` over `AsString()` (a reversal was itself reverted; reason unrecorded).
6. G-03 returns no failing IDs (release 1 adds them without changing the score).
Engine 1.4 will ship with its own baselines and a changelog of score changes.

## 10. Rollout
1. Step 0 (registration hardening) — own commit, live-verified.
2. Baseline capture (§7.1) — committed under `tests/live/baselines/`.
3. Engine + routes + tools — parity gate must pass.
4. Fix tool — fixture safety tests must pass.
5. Skill switch-over.
Each step reviewed before the next.

## 11. Licensing — DECIDED (option B)
Author decision (2026-10-02): AutoConst-authored code is under the **AutoConst Source Available
License** (same text as the scorecard repo): free to use and modify, including commercial use within
one's own organisation; **no resale, sublicensing, rebranding or paid-service distribution**.
The author retains the right to sell it.
- Upstream files (mcp-server-for-revit-python / Demolinator fork) remain **MIT** with their notices.
- AutoConst files carry a header: `# AutoConst Source Available License — see LICENSE-AUTOCONST`.
- Repo root: `LICENSE` (MIT, upstream, unchanged), `LICENSE-AUTOCONST` (new), `NOTICE` documents the
  split and which paths are which. Health engine/rules/routes/tools files are AutoConst files.
