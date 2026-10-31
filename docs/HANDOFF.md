# Install on another machine

This branch includes transcript discovery, Markdown export, and timestamp fixes recovered from local development. The library is pinned to a GitHub commit containing search support; no sibling checkout is required.

```sh
git clone --branch feat/transcript-research-handoff https://github.com/ChocoTonic/otterai-mcp.git
cd otterai-mcp
uv sync --frozen
```

Install uv first. The project requires Python 3.12 or later; uv can provision Python. Create a private credentials file, for example `~/.config/otter-mcp/.env`:

```dotenv
OTTERAI_USERNAME=your-email
OTTERAI_PASSWORD=your-password
```

On macOS/Linux, restrict access with `chmod 600 ~/.config/otter-mcp/.env`.
Add this to your Codex MCP configuration, replacing the example paths with absolute paths on the destination:

```toml
[mcp_servers.otter]
command = "/absolute/path/to/uv"
args = ["run", "--frozen", "--project", "/absolute/path/to/otterai-mcp", "otterai-mcp"]
startup_timeout_sec = 30.0
tool_timeout_sec = 120.0

[mcp_servers.otter.env]
OTTERAI_MCP_ENV_FILE = "/absolute/path/to/.config/otter-mcp/.env"
```

Restart the MCP client to refresh tool schemas. Ask it to list Otter folders to verify authentication. `uv run --frozen pytest -q` checks the local implementation without live credentials. Folder moves preview by default and require `confirm=true`. Markdown exports write locally and refuse overwrite by default.

## Change provenance

The local Codex logs contain the actual patch calls for these changes:

| Session ID | Work recovered |
| --- | --- |
| `01a05461-33ee-7c41-93eb-5f5c1e6cacc6` (August 30, 2026) | Original organizer and later requirements inventory; original organizer already committed |
| `01a07ca9-8b0b-78c0-8d05-305a3a0064e7` (September 7, 2026; patches September 8 UTC) | Library global search; MCP folder/date listing, pagination, search, URL fetch |
| `01a08a20-aad3-7253-80c9-41700b59ae33` (September 10, 2026) | Local Markdown export, search schema regression coverage, tick-to-millisecond conversion |

The development-only editable sibling dependency is replaced with a remote Git pin. Original source worktrees remain untouched. Unrelated scratch files are excluded. Conversation contents and credentials are not published.

Library prerequisite: https://github.com/ChocoTonic/otterai-py/pull/10
