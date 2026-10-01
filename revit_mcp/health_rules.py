# -*- coding: UTF-8 -*-
# AutoConst Source Available License - see LICENSE-AUTOCONST
"""
BIM Health Scorecard rule table (ruleset 1.3).

Faithful port of the rule definitions in the scorecard engine v1.3
(autoconst-claude-bim-health-scorecard, engine/score_model.py). Data only:
the scoring logic lives in health_engine.py. Known v1.3 quirks are preserved
on purpose for parity; see docs/design/bim_health_audit.md section 9.
"""

from pyrevit import DB

RULESET_VERSION = "1.3"
ENGINE_VERSION = "1.3"

STAGES = ("design", "fabrication", "operations")
SEV_FACTOR = {"fail": 1.0, "warn": 0.5, "info": 0.0}
CAT_WEIGHTS = {"naming": 0.15, "parameters": 0.35, "classification": 0.20,
               "geometry": 0.20, "worksharing": 0.10}
CATEGORY_ORDER = ["naming", "parameters", "classification", "geometry", "worksharing"]
GRADE = [("A", 90), ("B", 80), ("C", 70), ("D", 60), ("F", 0)]

BIC = DB.BuiltInCategory

# "design_only_na" reproduces v1.3's `na_allowed=(STAGE == "design")`,
# evaluated per request instead of at import time.
PARAM_RULES = [
    dict(cat="parameters", id="P-06", name="Doors: Type Mark/Width/Height",
         bic=BIC.OST_Doors, params=["Type Mark", "Width", "Height"], weight=2,
         severity="fail", src="LOD C1030"),
    dict(cat="parameters", id="P-06b", name="Door Fire Rating coverage",
         bic=BIC.OST_Doors, params=["Fire Rating"], weight=1, na_allowed=True,
         src="LOD/na"),
    dict(cat="parameters", id="P-06c", name="Door Operation type",
         bic=BIC.OST_Doors, params=["Operation"], weight=1, na_allowed=True,
         src="LOD C1030"),
    dict(cat="parameters", id="P-07", name="Windows: Type Mark/Width/Height",
         bic=BIC.OST_Windows, params=["Type Mark", "Width", "Height"], weight=1,
         severity="warn", src="LOD C1020"),
    dict(cat="parameters", id="P-07b", name="Window U-value coverage",
         bic=BIC.OST_Windows, params=["Analytic Construction"], weight=1,
         na_allowed=True, src="LOD C1020"),
    dict(cat="parameters", id="P-09", name="Struct framing: Structural Material",
         bic=BIC.OST_StructuralFraming, params=["Structural Material"], weight=2,
         severity="fail", src="LOD B1010"),
    dict(cat="parameters", id="P-09c", name="Struct columns: Structural Material",
         bic=BIC.OST_StructuralColumns, params=["Structural Material"], weight=2,
         severity="fail", src="LOD B1010"),
    # v1.3 quirk: na_allowed short-circuits severity_by_stage, so this is info at every stage
    dict(cat="parameters", id="P-09m", name="Struct members: Type Mark (fab ID)",
         bic=BIC.OST_StructuralFraming, params=["Type Mark"], weight=2,
         na_allowed=True, severity_by_stage={"design": "info", "fabrication": "fail"},
         src="LOD B1010"),
    dict(cat="parameters", id="P-04h", name="Mech equip: Manufacturer/Model",
         bic=BIC.OST_MechanicalEquipment, params=["Manufacturer", "Model"], weight=2,
         severity_by_stage={"design": "info", "operations": "fail"}, design_only_na=True,
         src="COBie Type"),
    dict(cat="parameters", id="P-04p", name="Plumbing fix: Manufacturer/Model",
         bic=BIC.OST_PlumbingFixtures, params=["Manufacturer", "Model"], weight=1,
         severity_by_stage={"design": "info", "operations": "fail"}, design_only_na=True,
         src="COBie Type"),
    dict(cat="parameters", id="P-04l", name="Lighting: Manufacturer/Model",
         bic=BIC.OST_LightingFixtures, params=["Manufacturer", "Model"], weight=1,
         severity_by_stage={"design": "info", "operations": "fail"}, design_only_na=True,
         src="COBie Type"),
    dict(cat="parameters", id="P-10", name="Rooms: Name/Number/Occupancy",
         bic=BIC.OST_Rooms, params=["Name", "Number", "Occupancy"], weight=2,
         severity="fail", src="COBie Space"),
]

# Classification: loadable families carry OmniClass + Uniformat, system families Uniformat only
OMNI_PATTERN = r'^[0-9]{2}(\.[0-9]{2})+$'
LOADABLE = [("Doors", BIC.OST_Doors), ("Windows", BIC.OST_Windows),
            ("Plumbing", BIC.OST_PlumbingFixtures), ("Lighting", BIC.OST_LightingFixtures),
            ("Furniture", BIC.OST_Furniture), ("Casework", BIC.OST_Casework),
            ("Framing", BIC.OST_StructuralFraming), ("Columns", BIC.OST_StructuralColumns),
            ("Foundations", BIC.OST_StructuralFoundation)]
SYSTEM = [("Walls", BIC.OST_Walls), ("Floors", BIC.OST_Floors),
          ("Roofs", BIC.OST_Roofs), ("Ceilings", BIC.OST_Ceilings)]

# Geometry thresholds (practitioner, Tier 3)
WARNINGS_WARN_ABOVE = 100
WARNINGS_FAIL_ABOVE = 1000
INPLACE_WARN_ABOVE = 10

ILLEGAL_NAME_PATTERN = r'[\\/:*?"<>|{}]'

# --- Assembly Code auto-fix (v1.3 fill policy) ---------------------------------
# Uniformat II Level-3 fallbacks, used only when a whole category is blank.
FIX_DEFAULTS = {
    "Framing": "B1010", "Columns": "B1010", "Foundations": "A1010",
    "Windows": "B2020", "Plumbing Fixtures": "D2010",
    "Lighting Fixtures": "D5020", "Casework": "E2010", "Furniture": "E2020",
}
FIX_CATEGORIES = [
    ("Framing", BIC.OST_StructuralFraming),
    ("Columns", BIC.OST_StructuralColumns),
    ("Foundations", BIC.OST_StructuralFoundation),
    ("Windows", BIC.OST_Windows),
    ("Plumbing Fixtures", BIC.OST_PlumbingFixtures),
    ("Lighting Fixtures", BIC.OST_LightingFixtures),
    ("Casework", BIC.OST_Casework),
    ("Furniture", BIC.OST_Furniture),
]

# Response limits
DEFAULT_MAX_FAILING_IDS = 200
MAX_TOTAL_FINDINGS = 20000
