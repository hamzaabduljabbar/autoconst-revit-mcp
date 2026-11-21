# AutoConst Revit MCP

Talk to your Revit model in plain English. Connect Claude (or any MCP client) to Revit and ask it to read, build, colour, audit and export.

By [Hamza Jabbar](https://hamzajabbar.online).

**Examples**
- "What's in this model?"
- "Which walls have no fire rating?"
- "Colour every wall by type"
- "Make a level, a grid and a sheet"
- "Export every room with its area"

## You need

- Windows + Revit 2024–2027 with a project open
- [pyRevit](https://github.com/pyrevitlabs/pyRevit/releases) (free Revit add-in)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Claude Desktop or Claude Code

## Setup (5 minutes)

**1. Download**

```powershell
git clone https://github.com/hamzaabduljabbar/autoconst-revit-mcp.git C:\autoconst-revit-mcp
cd C:\autoconst-revit-mcp
uv sync
```

**2. Load it into Revit**

```powershell
New-Item -ItemType Directory -Force C:\pyRevitExtensions
New-Item -ItemType Junction -Path C:\pyRevitExtensions\revit-mcp.extension -Target C:\autoconst-revit-mcp
```

In Revit: **pyRevit tab → Settings**
- Custom Extension Directories → add `C:\pyRevitExtensions`
- Routes → tick **Enable Routes Server**
- **Save Settings and Reload**

Check it: open <http://localhost:48884/revit_mcp/status/> in a browser. You should see `"status": "active"`.

**3. Connect Claude**

Claude Code:

```powershell
claude mcp add revit -- uv run --directory C:\autoconst-revit-mcp main.py
```

Claude Desktop: add this to `claude_desktop_config.json`, then restart Claude:

```json
{
  "mcpServers": {
    "revit": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\autoconst-revit-mcp", "main.py"]
    }
  }
}
```

Now ask Claude: *"What's in my Revit model?"*

## Supported Tools (48)

### Create (15)

| Tool | Description |
|------|-------------|
| `create_level` | Create new levels with elevations |
| `create_line_based_element` | Create walls, beams, and other line-based elements |
| `create_surface_based_element` | Create floors, roofs, and surface elements |
| `place_family` | Place a family instance at specified location |
| `create_grid` | Create column grid lines |
| `create_structural_framing` | Create structural beams and framing |
| `create_sheet` | Create new drawing sheets |
| `create_schedule` | Create schedules with custom fields |
| `create_room` | Create rooms at specified levels |
| `create_room_separation` | Create room separation boundary lines |
| `create_duct` | Create ducts between two points (MEP) |
| `create_pipe` | Create pipes between two points (MEP) |
| `create_mep_system` | Create mechanical or piping systems |
| `create_detail_line` | Create view-specific detail lines |
| `create_view` | Create floor plans, sections, elevations, 3D views |

### Query (12)

| Tool | Description |
|------|-------------|
| `get_revit_status` | Check if the API is active and responding |
| `get_revit_model_info` | Get model information |
| `list_levels` | Get all levels with elevations |
| `list_families` | Get available family types |
| `list_family_categories` | Get all family categories |
| `get_revit_view` | Export a view as an image |
| `list_revit_views` | List all exportable views |
| `get_current_view_info` | Get active view details |
| `get_current_view_elements` | Get elements in current view |
| `get_selected_elements` | Get currently selected elements |
| `list_category_parameters` | List parameters for a category |
| `get_element_properties` | Get all parameters and properties of an element |

### Modify (9)

| Tool | Description |
|------|-------------|
| `delete_elements` | Delete elements from the model |
| `modify_element` | Modify element parameter values |
| `color_splash` | Color elements by parameter values |
| `clear_colors` | Reset element colors |
| `tag_walls` | Tag all walls in current view |
| `set_parameter` | Set a single parameter value on an element |
| `tag_elements` | Tag specific elements with annotation symbols |
| `transform_elements` | Move, copy, rotate, or mirror elements |
| `set_active_view` | Switch the active view in Revit |

### Analyze (5)

| Tool | Description |
|------|-------------|
| `ai_element_filter` | Filter elements by category and parameters |
| `export_room_data` | Export room areas, volumes, boundaries |
| `get_material_quantities` | Material takeoff data |
| `check_clashes` | Detect hard clashes (interferences) between disciplines, e.g. structure vs MEP |
| `analyze_model_statistics` | Element counts and model stats |

### Document (2)

| Tool | Description |
|------|-------------|
| `create_dimensions` | Create dimension annotations |
| `export_document` | Export views to PDF or image |

### Interop & Persistence (4)

| Tool | Description |
|------|-------------|
| `export_ifc` | Export model to IFC format (IFC2x3/IFC4) |
| `link_file` | Link or import DWG, DXF, DGN, SAT, SKP, 3DM, or RVT files |
| `load_family` | Load a Revit family (`.rfa`) from disk so its types can be placed |
| `save_document` | Save / Save-As the model to disk (persistence across sessions) |

### Advanced (1)

| Tool | Description |
|------|-------------|
| `execute_revit_code` | Execute IronPython code in Revit context |

## If it doesn't work

| You see | Fix |
|---|---|
| Can't reach the page | Revit is closed, or Routes Server is off |
| 404 | The extension isn't loaded; check step 2 and reload pyRevit |
| Claude has no Revit tools | Restart Claude after adding the config |

Tip: try it on a copy of your model first.

## More

- Developer docs, all transports and config: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security: [SECURITY.md](SECURITY.md)

## License

AutoConst code is under the [AutoConst Source Available License](LICENSE-AUTOCONST); the open-source base is [MIT](LICENSE). See [NOTICE](NOTICE).
