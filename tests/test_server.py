import pytest

from otterai_mcp.server import create_server


class FakeService:
    def list_folders(self):
        return []

    def list_unsorted(self, page_size, cursor, start_date, end_date):
        return {"speeches": [], "next_cursor": None, "complete": True}

    def list_speeches(self, folder, page_size, cursor, start_date, end_date):
        return {"speeches": [], "next_cursor": None, "complete": True}

    def search_speeches(self, query, page_size, cursor, folder, start_date, end_date):
        return {"hits": [], "next_cursor": None, "complete": True}

    def get_speeches(self, speech_ids, include_transcript):
        return []

    def export_speeches_markdown(self, speech_ids, output_directory, overwrite):
        return {"format": "markdown+json", "files": []}

    def move_speeches(self, speech_ids, destination, confirm):
        return {"confirmed": confirm}


@pytest.mark.asyncio
async def test_server_advertises_only_focused_tools():
    server = create_server(service=FakeService())

    tools = {tool.name: tool for tool in await server.list_tools()}

    assert set(tools) == {
        "otter_list_folders",
        "otter_list_unsorted",
        "otter_list_speeches",
        "otter_search_speeches",
        "otter_get_speeches",
        "otter_move_speeches",
    }
    search_schema = tools["otter_search_speeches"].input_schema
    assert search_schema["required"] == ["query"]
    assert set(search_schema["properties"]) == {
        "query",
        "page_size",
        "cursor",
        "folder",
        "start_date",
        "end_date",
    }
    assert tools["otter_list_folders"].annotations.read_only_hint is True
    assert tools["otter_move_speeches"].annotations.read_only_hint is False
    assert tools["otter_move_speeches"].annotations.destructive_hint is False
