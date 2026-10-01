# -*- coding: UTF-8 -*-
# AutoConst Source Available License - see LICENSE-AUTOCONST
"""
BIM Health Scorecard engine (port of scorecard engine v1.3).

Scoring math is a faithful port of engine/score_model.py v1.3; parity is
checked against full-precision baselines in tests/live/baselines/.
The document and stage are always passed in explicitly; nothing is kept
in module-level state between requests.
"""

import json
import re

from pyrevit import DB

import health_rules as R

OMNI_RE = re.compile(R.OMNI_PATTERN)
ILLEGAL_RE = re.compile(R.ILLEGAL_NAME_PATTERN)


# --- helpers (v1.3 semantics) -----------------------------------------------

def _is_empty(v):
    return v is None or unicode(v).strip() in (u"", u"None")


def _pget(doc, elem, name):
    """Instance parameter by name, falling back to the type (v1.3 behaviour)."""
    p = elem.LookupParameter(name)
    if p is None:
        tid = elem.GetTypeId()
        if tid and tid != DB.ElementId.InvalidElementId:
            t = doc.GetElement(tid)
            if t:
                p = t.LookupParameter(name)
    if p is None:
        return None
    try:
        v = p.AsValueString()
        return v if v is not None else p.AsString()
    except Exception:
        return None


def _collect(doc, bic):
    return list(DB.FilteredElementCollector(doc).OfCategory(bic)
                .WhereElementIsNotElementType().ToElements())


def _eid(elem):
    try:
        return elem.Id.IntegerValue
    except AttributeError:  # Revit 2024+ also exposes .Value
        return int(elem.Id.Value)


def _resolve_sev(rule, stage):
    sbs = rule.get("severity_by_stage")
    return sbs.get(stage, rule.get("severity", "warn")) if sbs else rule.get("severity", "warn")


def _na_allowed(rule, stage):
    if rule.get("design_only_na"):
        return stage == "design"
    return bool(rule.get("na_allowed", False))


def letter(score):
    for g, lo in R.GRADE:
        if score >= lo:
            return g
    return "F"


# --- audit -------------------------------------------------------------------

class _Audit(object):
    def __init__(self, doc, stage):
        self.doc = doc
        self.stage = stage
        self.results = []        # v1.3 RESULTS, in v1.3 order
        self.not_applicable = []
        self.checked_ids = set()

    def add(self, cat, rid, name, weight, sev, passrate, fails, src="-", na=False,
            element_count=None, count_source="elements", findings=None, fail_count=None):
        self.results.append(dict(
            cat=cat, id=rid, name=name, weight=weight, severity=sev, passrate=passrate,
            fails=fails, src=src, na=na, element_count=element_count,
            count_source=count_source,
            findings=fails if findings is None else findings,
            fail_count=len(fails) if fail_count is None else fail_count))

    def skip(self, cat, rid, name, src, reason):
        self.not_applicable.append(dict(cat=cat, id=rid, name=name, src=src, reason=reason))

    # parameters
    def param_rule(self, r):
        els = _collect(self.doc, r["bic"])
        if not els:
            self.skip(r["cat"], r["id"], r["name"], r.get("src", "-"), "no elements in category")
            return
        na = _na_allowed(r, self.stage)
        fails = []
        for e in els:
            self.checked_ids.add(_eid(e))
            miss = [p for p in r["params"] if _is_empty(_pget(self.doc, e, p))]
            if miss:
                fails.append((_eid(e), ",".join(miss)))
        sev = "info" if na else _resolve_sev(r, self.stage)
        self.add(r["cat"], r["id"], r["name"], r["weight"], sev,
                 1.0 - len(fails) / float(len(els)), fails, src=r.get("src", "-"),
                 na=na, element_count=len(els))

    def rooms_placed(self):
        rooms = _collect(self.doc, R.BIC.OST_Rooms)
        if not rooms:
            self.skip("parameters", "P-11", "Rooms placed and area>0", "COBie Space",
                      "no rooms")
            return
        f = []
        for r in rooms:
            self.checked_ids.add(_eid(r))
            try:
                a = r.Area
            except Exception:
                a = 0
            if r.Location is None or a is None or a <= 0:
                f.append((_eid(r), "unplaced/area0"))
        self.add("parameters", "P-11", "Rooms placed and area>0", 2, "fail",
                 1.0 - len(f) / float(len(rooms)), f, src="COBie Space",
                 element_count=len(rooms))

    # classification
    def classification(self):
        for lab, bic in R.LOADABLE:
            els = _collect(self.doc, bic)
            if not els:
                self.skip("classification", "C-01/" + lab, "OmniClass (%s)" % lab,
                          "LOD/OC21", "no elements in category")
                self.skip("classification", "C-04/" + lab, "Uniformat (%s)" % lab,
                          "LOD/Uniformat", "no elements in category")
                continue
            for e in els:
                self.checked_ids.add(_eid(e))
            miss = [(_eid(e), "no OmniClass") for e in els
                    if _is_empty(_pget(self.doc, e, "OmniClass Number"))]
            acm = [(_eid(e), "no Assembly Code") for e in els
                   if _is_empty(_pget(self.doc, e, "Assembly Code"))]
            n = float(len(els))
            self.add("classification", "C-01/" + lab, "OmniClass (%s)" % lab, 2, "fail",
                     1.0 - len(miss) / n, miss, src="LOD/OC21", element_count=len(els))
            self.add("classification", "C-04/" + lab, "Uniformat (%s)" % lab, 1, "warn",
                     1.0 - len(acm) / n, acm, src="LOD/Uniformat", element_count=len(els))
        for lab, bic in R.SYSTEM:
            els = _collect(self.doc, bic)
            if not els:
                self.skip("classification", "C-05/" + lab, "Uniformat system (%s)" % lab,
                          "LOD/Uniformat", "no elements in category")
                continue
            for e in els:
                self.checked_ids.add(_eid(e))
            miss = [(_eid(e), "no Assembly Code") for e in els
                    if _is_empty(_pget(self.doc, e, "Assembly Code"))]
            self.add("classification", "C-05/" + lab, "Uniformat system (%s)" % lab, 2,
                     "fail", 1.0 - len(miss) / float(len(els)), miss, src="LOD/Uniformat",
                     element_count=len(els))

    # geometry
    @staticmethod
    def _tpass(c, wa=None, fa=None, tg=0):
        if fa is not None and c > fa:
            return 0.0
        if wa is not None and c > wa:
            return 0.5
        return 1.0 if c <= tg else 0.5

    def geometry(self):
        doc = self.doc
        w = doc.GetWarnings()
        nw = len(w)
        self.add("geometry", "G-01", "Revit warnings", 3, "fail",
                 self._tpass(nw, R.WARNINGS_WARN_ABOVE, R.WARNINGS_FAIL_ABOVE),
                 [(0, "%d warnings" % nw)] if w else [], src="practitioner",
                 count_source="aggregate", findings=[], fail_count=nw)
        ip = [f for f in DB.FilteredElementCollector(doc).OfClass(DB.Family) if f.IsInPlace]
        self.add("geometry", "G-02", "In-place families", 2, "fail",
                 self._tpass(len(ip), R.INPLACE_WARN_ABOVE, None, 0),
                 [(_eid(f), f.Name) for f in ip], src="practitioner")
        im = [i for i in DB.FilteredElementCollector(doc).OfClass(DB.ImportInstance).ToElements()
              if not i.IsLinked]
        # v1.3 reports no ids for G-03; the ids are listed here without changing the score
        self.add("geometry", "G-03", "Imported CAD", 2, "fail", 1.0 if not im else 0.0, [],
                 src="practitioner", count_source="aggregate",
                 findings=[(_eid(i), "imported CAD") for i in im], fail_count=len(im))

    # naming
    def naming(self):
        doc = self.doc
        lv = _collect(doc, R.BIC.OST_Levels)
        if lv:
            seen, bad = {}, []
            for l in lv:
                self.checked_ids.add(_eid(l))
                nm = getattr(l, "Name", "") or ""
                if _is_empty(nm):
                    bad.append((_eid(l), "unnamed"))
                elif nm in seen:
                    bad.append((_eid(l), "dup"))
                seen[nm] = 1
            self.add("naming", "N-03", "Levels named + unique", 1, "warn",
                     1.0 - len(bad) / float(len(lv)), bad, src="practitioner",
                     element_count=len(lv))
        else:
            self.skip("naming", "N-03", "Levels named + unique", "practitioner", "no levels")
        fams = list(DB.FilteredElementCollector(doc).OfClass(DB.Family).ToElements())
        if fams:
            nm2, bf = {}, []
            for f in fams:
                self.checked_ids.add(_eid(f))
                nm = getattr(f, "Name", "") or ""
                if ILLEGAL_RE.search(nm):
                    bf.append((_eid(f), "illegal"))
                if nm in nm2:
                    bf.append((_eid(f), "dup"))
                nm2[nm] = 1
            # one family can produce two findings -> counted as findings, not elements
            self.add("naming", "N-01", "Family names clean+unique", 2, "fail",
                     1.0 - len(bf) / float(len(fams)), bf, src="practitioner",
                     element_count=len(fams), count_source="findings")
        else:
            self.skip("naming", "N-01", "Family names clean+unique", "practitioner",
                      "no families")

    # worksharing
    def worksharing(self):
        if self.doc.IsWorkshared:
            self.add("worksharing", "W-01", "Worksharing enabled", 2, "warn", 1.0, [],
                     src="practitioner", count_source="aggregate")
        else:
            self.add("worksharing", "W-01", "Worksharing (standalone N/A)", 2, "info", 1.0, [],
                     src="practitioner", na=True, count_source="aggregate")

    def run(self):
        for r in R.PARAM_RULES:
            self.param_rule(r)
        self.rooms_placed()
        self.classification()
        self.geometry()
        self.naming()
        self.worksharing()

    def scores(self):
        cat_scores = {}
        for cat in R.CATEGORY_ORDER:
            rules = [r for r in self.results
                     if r["cat"] == cat and R.SEV_FACTOR.get(r["severity"], 0) > 0]
            if not rules:
                continue
            wsum = sum(r["weight"] * R.SEV_FACTOR[r["severity"]] for r in rules)
            psum = sum(r["weight"] * R.SEV_FACTOR[r["severity"]] * r["passrate"] for r in rules)
            cat_scores[cat] = 100.0 * psum / wsum if wsum else 100.0
        overall = (sum(R.CAT_WEIGHTS[c] * cat_scores[c] for c in cat_scores)
                   / sum(R.CAT_WEIGHTS[c] for c in cat_scores)) if cat_scores else 0.0
        return cat_scores, overall


def _doc_info(doc):
    return {"title": doc.Title, "path": doc.PathName or "", "is_workshared": doc.IsWorkshared}


def run_audit(doc, stage="design", max_failing_ids=R.DEFAULT_MAX_FAILING_IDS):
    """Run the full v1.3 audit. max_failing_ids=0 means no cap."""
    a = _Audit(doc, stage)
    a.run()
    cat_scores, overall = a.scores()

    total_findings = sum(len(r["findings"]) for r in a.results)
    complete_export = True
    error_code = None
    cap = max_failing_ids
    if cap == 0 and total_findings > R.MAX_TOTAL_FINDINGS:
        complete_export = False
        error_code = "export_too_large"
        cap = R.DEFAULT_MAX_FAILING_IDS

    rules_out = []
    for r in a.results:
        findings = sorted(r["findings"], key=lambda f: (f[0], f[1]))
        returned = findings if cap == 0 else findings[:cap]
        rules_out.append({
            "id": r["id"], "category": r["cat"], "name": r["name"],
            "severity": r["severity"], "weight": r["weight"], "source": r["src"],
            "advisory": bool(r["na"]), "applicable": True,
            "element_count": r["element_count"],
            "pass_rate": r["passrate"],
            "fail_count": r["fail_count"], "fail_count_source": r["count_source"],
            "distinct_failing_elements": (len(set(f[0] for f in r["findings"]))
                                          if r["count_source"] != "aggregate" else None),
            "findings_available": len(findings),
            "failing": [{"id": f[0], "reason": f[1]} for f in returned],
            "failing_returned": len(returned),
            "failing_truncated": len(findings) > len(returned),
        })
    for s in a.not_applicable:
        rules_out.append({
            "id": s["id"], "category": s["cat"], "name": s["name"], "source": s["src"],
            "applicable": False, "reason": s["reason"], "pass_rate": None,
            "fail_count": 0, "findings_available": 0, "failing": [],
            "failing_returned": 0, "failing_truncated": False,
        })

    scored = [c for c in R.CATEGORY_ORDER if c in cat_scores]
    not_scored = []
    for c in R.CATEGORY_ORDER:
        if c in cat_scores:
            continue
        ran = [r for r in a.results if r["cat"] == c]
        not_scored.append({"category": c, "reason": "only info-severity rules" if ran
                           else "no applicable rules"})

    out = {
        "status": "success",
        "engine_version": R.ENGINE_VERSION,
        "ruleset_version": R.RULESET_VERSION,
        "document": _doc_info(doc),
        "stage": stage,
        "overall": overall,
        "grade": letter(overall),
        "category_scores": cat_scores,
        "categories_scored": scored,
        "categories_not_scored": not_scored,
        "rules": rules_out,
        "complete_export": complete_export,
        "total_findings": total_findings,
        "summary": {
            "rules_run": len(a.results),
            "rules_scored": len([r for r in a.results
                                 if R.SEV_FACTOR.get(r["severity"], 0) > 0]),
            "rules_with_failures": len([r for r in a.results if r["fail_count"] > 0]),
            "rules_not_applicable": len(a.not_applicable),
            "unique_elements_checked": len(a.checked_ids),
        },
        "message": "Grade %s (%.1f/100), stage=%s" % (letter(overall), overall, stage),
    }
    if error_code:
        out["error_code"] = error_code
        out["message"] += "; findings capped: %d findings exceed the export limit of %d" % (
            total_findings, R.MAX_TOTAL_FINDINGS)
    return out


# --- Assembly Code fix (v1.3 fill policy, plan-bound apply) -----------------

def _type_name(t):
    p = t.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_NAME)
    if p and p.AsString():
        return p.AsString()
    return getattr(t, "Name", "") or ""


def build_fix_plan(doc):
    changes, skipped, cats = [], [], []
    for lab, bic in R.FIX_CATEGORIES:
        types = list(DB.FilteredElementCollector(doc).OfCategory(bic)
                     .WhereElementIsElementType().ToElements())
        if not types:
            continue
        freq, blanks = {}, []
        for t in types:
            ac = t.LookupParameter("Assembly Code")
            if ac is None:
                skipped.append({"type_id": _eid(t), "category": lab, "reason": "no_param"})
                continue
            if ac.IsReadOnly:
                skipped.append({"type_id": _eid(t), "category": lab, "reason": "param_read_only"})
                continue
            v = ac.AsString()
            if _is_empty(v):
                blanks.append(t)
            else:
                freq[v] = freq.get(v, 0) + 1
                skipped.append({"type_id": _eid(t), "category": lab,
                                "reason": "already_set", "current": v})
        if not blanks:
            continue
        # v1.3: modal code of the category; ties resolve like max() over the dict
        fill = max(freq, key=freq.get) if freq else R.FIX_DEFAULTS.get(lab, "")
        source = "modal" if freq else "default"
        if not fill:
            for t in blanks:
                skipped.append({"type_id": _eid(t), "category": lab, "reason": "no_fill_value"})
            continue
        cats.append({"category": lab, "blank_types": len(blanks), "fill_value": fill,
                     "fill_source": source})
        for t in blanks:
            cur = t.LookupParameter("Assembly Code").AsString() or ""
            changes.append({"type_id": _eid(t), "category": lab, "type_name": _type_name(t),
                            "current": cur, "proposed": fill, "fill_source": source})
    changes.sort(key=lambda c: c["type_id"])
    skipped.sort(key=lambda s: s["type_id"])
    return {"changes": changes, "skipped": skipped, "categories": cats}


def _sha256_hex(text):
    data = text.encode("utf-8")
    try:
        import hashlib
        return hashlib.sha256(data).hexdigest()
    except Exception:
        from System.Security.Cryptography import SHA256
        from System import Array, Byte
        digest = SHA256.Create().ComputeHash(Array[Byte](bytearray(data)))
        return "".join("%02x" % b for b in digest)


def plan_id(doc, plan):
    canonical = json.dumps({
        "fix": "assembly_code",
        "ruleset": R.RULESET_VERSION,
        "doc": [doc.Title, doc.PathName or "", doc.GetHashCode()],
        "changes": [[c["type_id"], c["current"], c["proposed"]] for c in plan["changes"]],
    }, sort_keys=True, separators=(",", ":"))
    return "sha256:" + _sha256_hex(canonical)


def preview_fix(doc):
    plan = build_fix_plan(doc)
    return {
        "status": "success", "mode": "preview",
        "plan_id": plan_id(doc, plan),
        "document": _doc_info(doc),
        "changes": plan["changes"], "skipped": plan["skipped"],
        "summary": {"to_change": len(plan["changes"]), "skipped": len(plan["skipped"]),
                    "categories": plan["categories"]},
        "message": "Preview: %d type(s) would get an Assembly Code. Nothing was written. "
                   "Apply with this plan_id." % len(plan["changes"]),
    }


class StalePlan(Exception):
    pass


def apply_fix(doc, expected_plan_id):
    """Apply a previewed plan. Raises StalePlan if the model no longer matches it."""
    plan = build_fix_plan(doc)
    current_id = plan_id(doc, plan)
    if current_id != expected_plan_id:
        raise StalePlan(current_id)
    if not plan["changes"]:
        return {"status": "success", "mode": "apply", "plan_id": current_id,
                "document": _doc_info(doc), "applied": [],
                "transaction": {"status": "not_started", "revit_status": None},
                "message": "Nothing to apply."}

    t = DB.Transaction(doc, "AutoConst: fill Assembly Codes")
    t.Start()
    applied = []
    try:
        for c in plan["changes"]:
            ty = doc.GetElement(_element_id(c["type_id"]))
            p = ty.LookupParameter("Assembly Code") if ty else None
            if p is None or p.IsReadOnly or not _is_empty(p.AsString()):
                raise StalePlan(current_id)
            p.Set(c["proposed"])
            applied.append({"type_id": c["type_id"], "category": c["category"],
                            "value": c["proposed"]})
        status = t.Commit()
    except StalePlan:
        _rollback(t)
        raise
    except Exception as e:
        raise RolledBack(_rollback(t), e)
    committed = status == DB.TransactionStatus.Committed
    return {
        "status": "success" if committed else "error",
        "mode": "apply", "plan_id": current_id, "document": _doc_info(doc),
        "applied": applied if committed else [],
        "transaction": {"status": "committed" if committed else "unknown",
                        "revit_status": str(status)},
        "message": ("Filled Assembly Code on %d type(s). One Ctrl+Z in Revit undoes it."
                    % len(applied)) if committed else
                   "Commit did not report success; re-run the preview to check the model state.",
    }


def _element_id(value):
    # Revit 2027 rejects ElementId(<int>) as ambiguous; Int64 works on 2024+
    try:
        import System
        return DB.ElementId(System.Int64(value))
    except Exception:
        return DB.ElementId(int(value))


def _rollback(t):
    """Roll back if still open; return Revit's TransactionStatus (or None)."""
    if t.HasStarted() and not t.HasEnded():
        return t.RollBack()
    return t.GetStatus()


class RolledBack(Exception):
    """Raised after a failed apply; carries Revit's RollBack() status and the cause."""
    def __init__(self, revit_status, cause):
        Exception.__init__(self, str(cause))
        self.revit_status = revit_status
        self.cause = cause
