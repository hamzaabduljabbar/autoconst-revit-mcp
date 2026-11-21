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
