# AutoConst Source Available License - see LICENSE-AUTOCONST
"""Print how the live design-stage audit differs from the v1.3 design baseline.

Usage:  uv run python tests/live/compare_to_baseline.py
"""
import glob
import json
import os

import httpx

API = "http://localhost:48884/revit_mcp"
BASE = glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "baselines", "*__design.json"))[0]

base = json.load(open(BASE, encoding="utf-8"))
got = httpx.post(API + "/health_audit/", json={"stage": "design", "max_failing_ids": 0},
                 timeout=300).json()
print("overall: baseline %.4f (%s) -> now %.4f (%s)" % (
    base["overall"], base["grade"], got["overall"], got["grade"]))
b = {r["id"]: r for r in base["rules"]}
changed = 0
for r in got["rules"]:
    if not r["applicable"]:
        continue
    br = b[r["id"]]
    # aggregate rules (G-01 warnings, G-03 imports) count differently from v1.3's fails list
    count_differs = (r["fail_count_source"] != "aggregate"
                     and r["fail_count"] != len(br["fails"]))
    if abs(r["pass_rate"] - br["passrate"]) > 1e-9 or count_differs:
        changed += 1
        print("  %-14s pass %.4f -> %.4f   fails %d -> %d" % (
            r["id"], br["passrate"], r["pass_rate"], len(br["fails"]), r["fail_count"]))
print("rules changed: %d" % changed)
