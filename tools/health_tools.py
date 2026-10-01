# -*- coding: utf-8 -*-
# AutoConst Source Available License - see LICENSE-AUTOCONST
"""BIM health audit tools: score a model A-F and fill blank Uniformat codes.

Unlike other tools, these return ONE JSON document as the whole text result
(success and error alike), so callers can json.loads() it directly.
"""

import json

from .utils import Context

HEALTH_TIMEOUT = 180.0


def _as_json(result) -> str:
    if isinstance(result, str):  # connection / timeout / 404 errors from the client
        result = {"status": "error", "error": result}
        if "did not answer" in result["error"]:
            result["error_code"] = "timeout"
            result["transaction"] = {"status": "unknown"}
    return json.dumps(result, indent=1, ensure_ascii=False, default=str)


def register_health_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register the BIM health audit tools with the MCP server."""
    _ = revit_get, revit_image

    @mcp.tool()
    async def bim_health_audit(
        stage: str = "design",
        max_failing_ids: int = 200,
        ctx: Context = None,
    ) -> str:
        """Audit the open Revit model's data quality and grade it A-F (read-only).

        Checks parameters (doors, windows, structure, MEP asset data, rooms),
        classification (OmniClass / Uniformat Assembly Code), geometry hygiene
        (warnings, in-place families, imported CAD), naming (levels, families)
        and worksharing. Returns the overall score and grade, a score per
        category, and every rule with its pass rate, fail count and the IDs
        of failing elements.

        Returns a single JSON document. Key fields: overall, grade,
        category_scores, rules[] (pass_rate, fail_count, failing[],
        failing_truncated), complete_export, message.

        Args:
            stage: "design" (default), "fabrication" or "operations".
                Later stages make asset data (Manufacturer/Model) count.
            max_failing_ids: Max failing element IDs listed per rule
                (default 200). 0 = no cap, for complete exports; counts and
                scores always cover the whole model either way.
            ctx: MCP context for logging
        """
        result = await revit_post(
            "/health_audit/",
            {"stage": stage, "max_failing_ids": max_failing_ids},
            ctx, timeout=HEALTH_TIMEOUT,
        )
        return _as_json(result)

    @mcp.tool()
    async def bim_health_fix(
        apply: bool = False,
        plan_id: str = None,
        ctx: Context = None,
    ) -> str:
        """Fill blank Uniformat "Assembly Code" values on element types (two steps).

        Step 1 - preview (apply=false, the default): returns every type that
        would change, its current and proposed value, skipped types with
        reasons, and a plan_id. Nothing is written. Show this to the user.

        Step 2 - apply (apply=true, plan_id=<from the preview>): writes exactly
        that plan in one Revit transaction (one Ctrl+Z undoes it). If the model
        changed since the preview, nothing is written and a fresh preview is
        returned (error_code "stale_plan").

        Covers Structural Framing/Columns/Foundations, Windows, Plumbing and
        Lighting Fixtures, Casework and Furniture. Never overwrites an existing
        code. The fill value is the category's most common existing code, or a
        Uniformat default if the whole category is blank.

        If an apply call times out, the outcome is unknown (Revit may have
        committed): run a preview or bim_health_audit to check the model before
        retrying. Never re-apply blind.

        Args:
            apply: false = preview only (default); true = write the plan.
            plan_id: Required when apply=true; the plan_id from the preview.
            ctx: MCP context for logging
        """
        payload = {"fix": "assembly_code", "apply": bool(apply)}
        if plan_id:
            payload["plan_id"] = plan_id
        result = await revit_post("/health_fix/", payload, ctx, timeout=HEALTH_TIMEOUT)
        return _as_json(result)
