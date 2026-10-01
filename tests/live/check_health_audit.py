# AutoConst Source Available License - see LICENSE-AUTOCONST
"""Live parity check: /health_audit/ vs the captured v1.3 baselines.

Requires Revit running with the baseline model open and the extension reloaded.
Usage:  uv run python tests/live/check_health_audit.py
"""
import glob
import json
import os
import sys
import time

import httpx

API = "http://localhost:48884/revit_mcp"
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baselines")
TOL = 1e-9
AGGREGATE = {"G-01", "G-03"}  # new count fields; v1.3 len(fails) parity does not apply


def check(baseline_path):
    base = json.load(open(baseline_path, encoding="utf-8"))
    stage = base["provenance"]["stage"]
    t0 = time.time()
    r = httpx.post(API + "/health_audit/", json={"stage": stage, "max_failing_ids": 0},
                   timeout=300)
    secs = time.time() - t0
    r.raise_for_status()
    got = r.json()
    errs = []

    if got["document"]["title"] != base["document"]["title"]:
        return ["wrong model open: %s" % got["document"]["title"]], secs, len(r.content)

    if abs(got["overall"] - base["overall"]) > TOL:
        errs.append("overall %r != %r" % (got["overall"], base["overall"]))
    if got["grade"] != base["grade"]:
        errs.append("grade %s != %s" % (got["grade"], base["grade"]))
    if set(got["category_scores"]) != set(base["category_scores"]):
        errs.append("categories %s != %s" % (sorted(got["category_scores"]),
                                             sorted(base["category_scores"])))
    for c, v in base["category_scores"].items():
        if c in got["category_scores"] and abs(got["category_scores"][c] - v) > TOL:
            errs.append("category %s %r != %r" % (c, got["category_scores"][c], v))

    g = {x["id"]: x for x in got["rules"] if x["applicable"]}
    b = {x["id"]: x for x in base["rules"]}
    if list(g) != list(b):
        errs.append("rule set/order differs: only new %s, only base %s" % (
            sorted(set(g) - set(b)), sorted(set(b) - set(g))))
    for rid, br in b.items():
        gr = g.get(rid)
        if not gr:
            continue
        if gr["severity"] != br["severity"]:
            errs.append("%s severity %s != %s" % (rid, gr["severity"], br["severity"]))
        if bool(gr["advisory"]) != bool(br["na"]):
            errs.append("%s advisory %s != %s" % (rid, gr["advisory"], br["na"]))
        if abs(gr["pass_rate"] - br["passrate"]) > TOL:
            errs.append("%s pass_rate %r != %r" % (rid, gr["pass_rate"], br["passrate"]))
        if rid not in AGGREGATE:
            if gr["fail_count"] != len(br["fails"]):
                errs.append("%s fail_count %d != %d" % (rid, gr["fail_count"], len(br["fails"])))
            got_f = sorted((f["id"], f["reason"]) for f in gr["failing"])
            base_f = sorted((f[0], f[1]) for f in br["fails"])
            if got_f != base_f:
                errs.append("%s failing findings differ" % rid)
        if gr["failing_truncated"]:
            errs.append("%s truncated in an uncapped audit" % rid)

    # G-01: fail_count = warning count from v1.3's "<n> warnings" entry
    g01 = g.get("G-01")
    if g01 and b["G-01"]["fails"]:
        n = int(b["G-01"]["fails"][0][1].split()[0])
        if g01["fail_count"] != n or g01["findings_available"] != 0:
            errs.append("G-01 fail_count %s (expected %d), findings_available %s" % (
                g01["fail_count"], n, g01["findings_available"]))

    if not got["complete_export"]:
        errs.append("complete_export is false")
    rows = sum(x["findings_available"] for x in got["rules"])
    if rows != got["total_findings"]:
        errs.append("total_findings %d != sum findings_available %d" % (got["total_findings"], rows))
    return errs, secs, len(r.content)


def main():
    paths = sorted(glob.glob(os.path.join(BASE_DIR, "*.json")))
    if not paths:
        sys.exit("no baselines in %s" % BASE_DIR)
    failed = False
    for p in paths:
        errs, secs, size = check(p)
        name = os.path.basename(p)
        print("%-60s %s  (%.1fs, %d KB)" % (name, "PASS" if not errs else "FAIL", secs, size // 1024))
        for e in errs:
            print("    - " + e)
        failed = failed or bool(errs)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
