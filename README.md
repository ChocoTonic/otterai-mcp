# otterai-mcp

Focused MCP server for inspecting and organizing Otter.ai conversations. All
Otter operations are delegated to
[`ChocoTonic/otterai-py`](https://github.com/ChocoTonic/otterai-py); this server
does not implement or call Otter endpoints directly.

## Tools

- `otter_list_folders`: list exact remote folder names, IDs, and counts.
- `otter_list_unsorted`: list only owned conversations with no folder.
- `otter_get_speeches`: fetch safe metadata and optional transcripts by ID.
- `otter_move_speeches`: preview or confirm verified folder moves.

No upload, delete, recording, speaker, notification, group, or arbitrary API
tools are exposed.

## Configuration

Set credentials directly:

```bash
export OTTERAI_USERNAME="you@example.com"
export OTTERAI_PASSWORD="..."
```

The legacy variable names `OTTER_USERNAME` and `OTTER_PASSWORD` are also
accepted. To load an existing dotenv file from another directory:

```bash
export OTTERAI_MCP_ENV_FILE="/absolute/path/to/.env"
```

## Run

```bash
uv sync
uv run otterai-mcp
```

The server uses stdio transport. Folder moves default to preview mode and
require `confirm=true` before changing remote state. Confirmed moves are read
back from Otter and fail if the destination cannot be verified.

