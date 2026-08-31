"""MCP server construction and focused tool registration."""

from __future__ import annotations

from functools import partial
from typing import Annotated, Any

from anyio import to_thread
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from . import __version__
from .service import OtterService
from .settings import Settings

PageSize = Annotated[int, Field(ge=1, le=100)]
SpeechIds = Annotated[list[str], Field(min_length=1, max_length=10)]


async def _thread(callback: Any, /, *args: Any, **kwargs: Any) -> Any:
    return await to_thread.run_sync(partial(callback, *args, **kwargs))


def create_server(
    settings: Settings | None = None, *, service: OtterService | None = None
) -> MCPServer:
    runtime = service or OtterService(settings or Settings.from_env())
    server = MCPServer(
        name="otterai-mcp",
        title="Otter.ai Organizer",
        description="Focused remote folder inventory and conversation organization.",
        version=__version__,
        instructions=(
            "Use otter_list_unsorted for authoritative unfiled conversations. "
            "Preview every move with confirm=false before setting confirm=true."
        ),
    )

    @server.tool(
        name="otter_list_folders",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
    )
    async def list_folders() -> list[dict[str, Any]]:
        """List every remote folder with exact ID, name, and speech count."""
        return await _thread(runtime.list_folders)

    @server.tool(
        name="otter_list_unsorted",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
    )
    async def list_unsorted(
        page_size: PageSize = 25, cursor: int | None = None
    ) -> dict[str, Any]:
        """List only owned conversations with no remote folder assignment."""
        return await _thread(runtime.list_unsorted, page_size, cursor)

    @server.tool(
        name="otter_get_speeches",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
    )
    async def get_speeches(
        speech_ids: SpeechIds, include_transcript: bool = True
    ) -> list[dict[str, Any]]:
        """Fetch exact conversations with safe metadata and optional transcripts."""
        return await _thread(runtime.get_speeches, speech_ids, include_transcript)

    @server.tool(
        name="otter_move_speeches",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=True,
        ),
    )
    async def move_speeches(
        speech_ids: SpeechIds, destination_folder: str, confirm: bool = False
    ) -> dict[str, Any]:
        """Preview or confirm verified moves to one existing remote folder."""
        return await _thread(
            runtime.move_speeches, speech_ids, destination_folder, confirm
        )

    return server

