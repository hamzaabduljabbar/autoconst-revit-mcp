# AutoConst Source Available License - see LICENSE-AUTOCONST
"""Capture a full-precision baseline from the UNMODIFIED BIM Health Scorecard engine v1.3.

The v1.3 engine only prints rounded text, so this script makes exactly two textual
changes to engine/score_model.py (read at a pinned git commit of the scorecard repo):
  1. sets STAGE to the requested stage
  2. strips the trailing print block
then appends a serializer that emits the in-memory results as JSON.

Requires Revit running with pyRevit Routes and the target model open.

Usage:
  uv run python tests/live/capture_v13_baseline.py [--stages design fabrication operations]
"""
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys

import httpx

SCORECARD_REPO = os.environ.get(
    "SCORECARD_REPO", r"C:\Users\Hamza\autoconst-claude-bim-health-scorecard")
ENGINE_COMMIT = "c9e988761e7a2025ab2a8bf9744df2c47c01135f"
ENGINE_PATH = "engine/score_model.py"
API = "http://localhost:48884/revit_mcp"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baselines")

PRINT_BLOCK = 'print("=" * 66)\nprint("BIM HEALTH SCORECARD'
STAGE_LINE = 'STAGE = "design"'

SERIALIZER = '''
import json as _json
_out = {
    "overall": overall,
    "grade": letter(overall),
    "category_scores": cat_scores,
    "rules": RESULTS,
    "document": {"title": doc.Title, "path": doc.PathName,
                 "is_workshared": doc.IsWorkshared,
                 "revit_version": doc.Application.VersionNumber,
                 "revit_build": doc.Application.VersionBuild},
}
print("@@BASELINE@@" + _json.dumps(_out) + "@@END@@")
'''


def engine_source():
    src = subprocess.check_output(
        ["git", "-C", SCORECARD_REPO, "show", "%s:%s" % (ENGINE_COMMIT, ENGINE_PATH)])
    return src.decode("utf-8").replace("\r\n", "\n")


def build_script(src, stage):
    assert src.count(STAGE_LINE) == 1, "STAGE line not found exactly once"
    assert src.count(PRINT_BLOCK) == 1, "print block not found exactly once"
    src = src.replace(STAGE_LINE, 'STAGE = "%s"' % stage)
    src = src[: src.index(PRINT_BLOCK)]
    return src + SERIALIZER


def capture(stage, src):
    code = build_script(src, stage)
    r = httpx.post(API + "/execute_code/", json={
        "code": code, "description": "v1.3 baseline capture (%s)" % stage}, timeout=300)
    r.raise_for_status()
    out = r.json().get("output", "")
    if "@@BASELINE@@" not in out:
        sys.exit("capture failed for %s:\n%s" % (stage, json.dumps(r.json(), indent=1)[:3000]))
    data = json.loads(out.split("@@BASELINE@@", 1)[1].split("@@END@@", 1)[0])
    path = data["document"]["path"]
    data["provenance"] = {
        "engine_version": "1.3",
        "engine_repo": SCORECARD_REPO,
        "engine_commit": ENGINE_COMMIT,
        "capture_script_sha256": hashlib.sha256(open(__file__, "rb").read()).hexdigest(),
        "stage": stage,
        "captured_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "model_file_size": os.path.getsize(path) if path and os.path.exists(path) else None,
        "model_file_mtime": (datetime.datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
                             if path and os.path.exists(path) else None),
    }
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", nargs="+", default=["design", "fabrication", "operations"])
    args = ap.parse_args()
    src = engine_source()
    os.makedirs(OUT_DIR, exist_ok=True)
    for stage in args.stages:
        data = capture(stage, src)
        slug = "".join(c if c.isalnum() else "_" for c in data["document"]["title"]).strip("_")
        out = os.path.join(OUT_DIR, "%s__%s.json" % (slug, stage))
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        print("%-12s overall=%r grade=%s rules=%d -> %s" % (
            stage, data["overall"], data["grade"], len(data["rules"]), out))


if __name__ == "__main__":
    main()
