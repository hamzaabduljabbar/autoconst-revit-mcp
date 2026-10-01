# -*- coding: utf-8 -*-
"""
Documentation tools - sheets, schedules, and document export

FILE LOCATION: tools/documentation_tools.py
RUNS ON:       MCP Server (Python 3, outside Revit)
PURPOSE:       Defines the MCP tools that Claude can call. Each tool
               packages up parameters and sends an HTTP POST to the
               Revit-side route handler (revit_mcp/documentation.py).
"""

from .utils import Context, format_response


def register_documentation_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register documentation tools with the MCP server."""
    _ = revit_image

    @mcp.tool()
    async def create_sheet(
        sheet_number: str = None,
        sheet_name: str = "Unnamed Sheet",
        title_block_name: str = None,
        ctx: Context = None,
    ) -> str:
        """Create a drawing sheet in Revit for construction documentation.

        Sheets are the printable output of a Revit project. Each sheet has a
        title block, sheet number, and name. Views can be placed on sheets
        after creation.

        Args:
            sheet_number: Sheet number, e.g. "A101" (optional, auto-assigned)
            sheet_name: Sheet title, e.g. "Ground Floor Plan" (defaults to "Unnamed Sheet")
            title_block_name: Title block family name (optional, uses first available)
            ctx: MCP context for logging
        """
        data = {
            "sheet_number": sheet_number,
            "sheet_name": sheet_name,
            "title_block_name": title_block_name,
        }
        response = await revit_post("/create_sheet/", data, ctx)
        return format_response(response)

    @mcp.tool()
    async def bulk_create_sheets(
        sheets: list[dict],
        ctx: Context = None,
    ) -> str:
        """Create multiple drawing sheets in a single batch operation.

        Accepts a list of sheet definitions and creates them all at once,
        with duplicate detection, title-block fallback, and per-sheet
        error handling. Much faster than calling create_sheet in a loop.

        Use this when the user wants to set up multiple sheets at once,
        for example from a sheet index or drawing register.

        Returns a JSON summary with created/skipped/failed counts and
        per-sheet results including element IDs.

        Args:
            sheets: List of sheet definitions. Each dict must have:
                - sheet_number (str, required): Unique number like "A-101"
                - sheet_name (str, required): Title like "Ground Floor Plan"
                - title_block_family_type (str, optional): "FamilyName: TypeName"
                  Falls back to first available title block if omitted or not found.
            ctx: MCP context for logging
        """
        data = {"sheets": sheets}
        response = await revit_post("/bulk_create_sheets/", data, ctx)
        return format_response(response)

    @mcp.tool()
    async def create_schedule(
        category: str,
        fields: list[str] = None,
        schedule_name: str = None,
        ctx: Context = None,
    ) -> str:
        """Create a schedule (quantity takeoff view) for a specific element category.

        Schedules tabulate element data, for example a wall schedule showing
        all walls with their types, lengths, and areas. The schedule appears
        as a new view in the Revit project browser.

        Args:
            category: BuiltInCategory name, e.g. "OST_Walls", "OST_Rooms" (required)
            fields: Parameter names to include as columns (optional, uses default set)
                e.g., ["Family and Type", "Length", "Area", "Mark"]
            schedule_name: Name for the schedule view (optional, auto-generated)
            ctx: MCP context for logging
        """
        data = {
            "category": category,
            "fields": fields,
            "schedule_name": schedule_name,
        }
        response = await revit_post("/create_schedule/", data, ctx)
        return format_response(response)

    @mcp.tool()
    async def export_document(
        view_name: str = None,
        format: str = "pdf",
        resolution: int = 300,
        ctx: Context = None,
    ) -> str:
        """Export a Revit view or sheet to PDF or image format.

        Exports the specified view (or the active view if none specified) to a
        file on disk. Supported formats: PDF, PNG, JPG, DWG.

        Args:
            view_name: Name of the view or sheet to export (optional, uses active view)
            format: Output format - "pdf", "png", "jpg", or "dwg" (defaults to "pdf")
            resolution: DPI for image formats (defaults to 300, ignored for PDF/DWG)
            ctx: MCP context for logging
        """
        data = {
            "view_name": view_name,
            "format": format,
            "resolution": resolution,
        }
        response = await revit_post("/export_document/", data, ctx)
        return format_response(response)
