# -*- coding: UTF-8 -*-
"""
Revit MCP Extension Startup
Registers all MCP routes and initializes the API.

Each route module is registered in isolation: a module that fails to import or
register is logged and skipped, and every other module still loads. The
/routes_status/ route reports which modules loaded and which failed.
"""

from pyrevit import routes
import json
import logging
import traceback

logger = logging.getLogger(__name__)

# Initialize the main API
api = routes.API("revit_mcp")

# (module path, register function name)
ROUTE_MODULES = [
    ("revit_mcp.status", "register_status_routes"),
    ("revit_mcp.model_info", "register_model_info_routes"),
    ("revit_mcp.views", "register_views_routes"),
    ("revit_mcp.placement", "register_placement_routes"),
    ("revit_mcp.colors", "register_color_routes"),
    ("revit_mcp.code_execution", "register_code_execution_routes"),
    ("revit_mcp.building", "register_building_routes"),
    ("revit_mcp.editing", "register_editing_routes"),
    ("revit_mcp.structure", "register_structure_routes"),
    ("revit_mcp.annotation", "register_annotation_routes"),
    ("revit_mcp.analysis", "register_analysis_routes"),
    ("revit_mcp.documentation", "register_documentation_routes"),
    ("revit_mcp.rooms", "register_room_routes"),
    ("revit_mcp.view_management", "register_view_management_routes"),
    ("revit_mcp.tags", "register_tag_routes"),
    ("revit_mcp.transforms", "register_transform_routes"),
    ("revit_mcp.mep", "register_mep_routes"),
    ("revit_mcp.parameters", "register_parameter_routes"),
    ("revit_mcp.interop", "register_interop_routes"),
    ("revit_mcp.detail", "register_detail_routes"),
    ("revit_mcp.clash", "register_clash_routes"),
    ("revit_mcp.document", "register_document_routes"),
    ("revit_mcp.health_routes", "register_health_routes"),
]

REGISTRY = {"loaded": [], "failed": []}


# Registered first and depends on nothing else, so it survives any module failure
@api.route("/routes_status/", methods=["GET"])
def routes_status():
    return routes.make_response(
        data={
            "status": "success",
            "loaded_count": len(REGISTRY["loaded"]),
            "failed_count": len(REGISTRY["failed"]),
            "loaded": REGISTRY["loaded"],
            "failed": REGISTRY["failed"],
        }
    )


def register_routes():
    """Register every route module, isolating failures per module."""
    for module_path, func_name in ROUTE_MODULES:
        try:
            module = __import__(module_path, fromlist=[func_name])
            getattr(module, func_name)(api)
            REGISTRY["loaded"].append(module_path)
        except Exception as e:
            REGISTRY["failed"].append({
                "module": module_path,
                "error": str(e),
                "traceback": traceback.format_exc(),
            })
            logger.error("Failed to register %s: %s", module_path, str(e))

    if REGISTRY["failed"]:
        logger.error(
            "MCP routes: %d loaded, %d FAILED: %s",
            len(REGISTRY["loaded"]), len(REGISTRY["failed"]),
            json.dumps([f["module"] for f in REGISTRY["failed"]]),
        )
    else:
        logger.info("All %d MCP route modules registered", len(REGISTRY["loaded"]))


# Register all routes when the extension loads
register_routes()
