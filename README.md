# otterai-mcp

Focused MCP server for inspecting and organizing Otter.ai conversations. All
Otter operations are delegated to
[`ChocoTonic/otterai-py`](https://github.com/ChocoTonic/otterai-py); this server
does not implement or call Otter endpoints directly.

## Tools

- `otter_list_folders`: list exact remote folder names, IDs, and counts.
- `otter_list_unsorted`: list only owned conversations with no folder.
- `otter_list_speeches`: list owned or folder-scoped conversations with dates and pagination.
- `otter_search_speeches`: search transcript text with speaker-labeled snippets.
- `otter_get_speeches`: fetch safe metadata and optional transcripts by ID.
- `otter_export_speeches_markdown`: write lossless normalized transcript payloads
  to local Markdown files without changing Otter.
- `otter_move_speeches`: preview or confirm verified folder moves.

`otter_get_speeches` accepts raw IDs and `https://otter.ai/u/...` URLs. No
upload, download, delete, recording, speaker, notification, group, account, or
arbitrary API tools are exposed.

Markdown export requires an absolute output directory. It refuses to replace an
existing file unless `overwrite=true`; each file embeds the complete normalized
speech payload as JSON so transcript segment text, speakers, and timestamps are
not dropped or reflowed.

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

## Install on another machine

See [the handoff guide](docs/HANDOFF.md) for clone instructions, MCP configuration,
credential setup, validation, and change provenance.
