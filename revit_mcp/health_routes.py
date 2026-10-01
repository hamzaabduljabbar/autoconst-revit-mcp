# -*- coding: UTF-8 -*-
# AutoConst Source Available License - see LICENSE-AUTOCONST
"""
BIM health audit routes: /health_audit/ (read-only) and /health_fix/ (writes).
"""

import json
import logging
import traceback

from pyrevit import routes

import health_engine as E
import health_rules as R

logger = logging.getLogger(__name__)


def _payload(request):
    if request and request.data:
        return json.loads(request.data) if isinstance(request.data, str) else request.data
    return {}


def _error(message, status, **extra):
    data = {"status": "error", "error": message}
    data.update(extra)
    return routes.make_response(data=data, status=status)


def register_health_routes(api):

    @api.route("/health_audit/", methods=["POST"])
    def health_audit(doc, request):
        try:
            if not doc:
                return _error("No active Revit document", 503)
            data = _payload(request)
            stage = data.get("stage", "design")
            if stage not in R.STAGES:
                return _error("stage must be one of: %s" % ", ".join(R.STAGES), 400)
            cap = data.get("max_failing_ids", R.DEFAULT_MAX_FAILING_IDS)
            if not isinstance(cap, int) or isinstance(cap, bool) or cap < 0:
                return _error("max_failing_ids must be an integer >= 0 (0 = no cap)", 400)
            return routes.make_response(data=E.run_audit(doc, stage, cap))
        except Exception as e:
            logger.error("health_audit failed: %s", str(e))
            return _error(str(e), 500, traceback=traceback.format_exc())

    @api.route("/health_fix/", methods=["POST"])
    def health_fix(doc, request):
        try:
            if not doc:
                return _error("No active Revit document", 503)
            data = _payload(request)
            if data.get("fix", "assembly_code") != "assembly_code":
                return _error("fix must be 'assembly_code'", 400)
            if not data.get("apply"):
                return routes.make_response(data=E.preview_fix(doc))
            expected = data.get("plan_id")
            if not expected:
                return _error("apply=true requires the plan_id returned by a preview", 400)
            try:
                return routes.make_response(data=E.apply_fix(doc, expected))
            except E.StalePlan:
                return _error(
                    "stale_plan: the model changed since the preview; nothing was written. "
                    "Review the fresh preview and apply its plan_id.", 409,
                    error_code="stale_plan",
                    transaction={"status": "rolled_back_or_not_started"},
                    fresh_preview=E.preview_fix(doc))
            except E.RolledBack as rb:
                return _error(
                    "apply failed and was rolled back: %s" % rb.cause, 500,
                    error_code="apply_failed",
                    transaction={"status": "rolled_back", "revit_status": str(rb.revit_status)},
                    traceback=traceback.format_exc())
        except Exception as e:
            logger.error("health_fix failed: %s", str(e))
            return _error(str(e), 500, transaction={"status": "unknown"},
                          traceback=traceback.format_exc())
