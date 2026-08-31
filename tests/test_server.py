import pytest

from otterai_mcp.server import create_server


class FakeService:
    def list_folders(self):
        return []

    def list_unsorted(self, page_size, cursor):
        return {"speeches": [], "next_cursor": None, "complete": True}

    def get_speeches(self, speech_ids, include_transcript):
        return []

    def move_speeches(self, speech_ids, destination, confirm):
        return {"confirmed": confirm}


@pytest.mark.asyncio
async def test_server_advertises_only_focused_tools():
    server = create_server(service=FakeService())

    tools = {tool.name: tool for tool in await server.list_tools()}

    assert set(tools) == {
        "otter_list_folders",
        "otter_list_unsorted",
        "otter_get_speeches",
        "otter_move_speeches",
    }
    assert tools["otter_list_folders"].annotations.read_only_hint is True
    assert tools["otter_move_speeches"].annotations.read_only_hint is False
    assert tools["otter_move_speeches"].annotations.destructive_hint is False

