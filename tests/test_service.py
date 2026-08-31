from unittest.mock import Mock

import pytest

from otterai_mcp.service import OtterService
from otterai_mcp.settings import Settings


def response(data):
    return {"status": 200, "data": data}


@pytest.fixture
def client():
    result = Mock()
    result.get_folders.return_value = response(
        {
            "folders": [
                {"id": 2, "folder_name": "2_work", "speech_count": 5},
                {"id": 1, "folder_name": "1_general", "speech_count": 3},
            ]
        }
    )
    return result


@pytest.fixture
def service(client):
    return OtterService(Settings("user", "password"), client=client)


def test_list_folders_normalizes_and_sorts(service):
    assert service.list_folders() == [
        {"id": 1, "name": "1_general", "speech_count": 3},
        {"id": 2, "name": "2_work", "speech_count": 5},
    ]


def test_list_unsorted_uses_library_and_strips_raw_fields(service, client):
    client.list_unsorted_speeches.return_value = response(
        {
            "speeches": [
                {
                    "otid": "speech-1",
                    "title": "Call",
                    "folder": None,
                    "pubsub_jwt": "must-not-leak",
                }
            ],
            "end_of_list": False,
            "last_load_ts": 123,
        }
    )

    result = service.list_unsorted(page_size=10, cursor=456)

    client.list_unsorted_speeches.assert_called_once_with(
        page_size=10, last_load_ts=456
    )
    assert result["next_cursor"] == 123
    assert result["speeches"][0]["id"] == "speech-1"
    assert "pubsub_jwt" not in result["speeches"][0]


def test_get_speeches_normalizes_transcript(service, client):
    client.get_speech.return_value = response(
        {
            "speech": {
                "otid": "speech-1",
                "title": "Call",
                "folder": {"id": 1, "folder_name": "1_general"},
                "speakers": [{"id": 7, "speaker_name": "Steve"}],
                "transcripts": [
                    {
                        "speaker_id": 7,
                        "start_offset": 10,
                        "end_offset": 20,
                        "transcript": "Hello",
                    }
                ],
            }
        }
    )

    result = service.get_speeches(["speech-1"])

    assert result[0]["folder"] == {"id": 1, "name": "1_general"}
    assert result[0]["transcript"] == [
        {"speaker": "Steve", "start_ms": 10, "end_ms": 20, "text": "Hello"}
    ]


def test_get_speeches_accepts_null_outline_and_transcript(service, client):
    client.get_speech.return_value = response(
        {
            "speech": {
                "otid": "speech-1",
                "title": "Untitled",
                "speech_outline": None,
                "transcripts": None,
            }
        }
    )

    result = service.get_speeches(["speech-1"])

    assert result[0]["outline"] == []
    assert result[0]["transcript"] == []


def test_move_preview_does_not_mutate(service, client):
    client.get_speech.return_value = response(
        {"speech": {"otid": "speech-1", "title": "Call", "folder": None}}
    )

    result = service.move_speeches(["speech-1"], "2_work", confirm=False)

    assert result["confirmed"] is False
    client.move_speeches_to_folder.assert_not_called()


def test_move_uses_library_and_verifies(service, client):
    client.get_speech.side_effect = [
        response(
            {"speech": {"otid": "speech-1", "title": "Call", "folder": None}}
        ),
        response(
            {
                "speech": {
                    "otid": "speech-1",
                    "title": "Call",
                    "folder": {"id": 2, "folder_name": "2_work"},
                }
            }
        ),
    ]
    client.move_speeches_to_folder.return_value = response({"status": "OK"})

    result = service.move_speeches(["speech-1"], "2_work", confirm=True)

    client.move_speeches_to_folder.assert_called_once_with(2, ["speech-1"])
    assert result["changed"] is True
    assert result["destination"] == {"id": 2, "name": "2_work"}
    assert result["speeches"][0]["folder"]["id"] == 2


def test_move_rejects_unknown_folder(service):
    with pytest.raises(ValueError, match="unknown destination"):
        service.move_speeches(["speech-1"], "missing", confirm=False)
