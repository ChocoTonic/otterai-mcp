from datetime import date
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


def test_list_speeches_supports_owned_pagination_and_dates(service, client):
    client.get_speeches.return_value = response(
        {
            "speeches": [
                {
                    "otid": "inside",
                    "title": "Inside range",
                    "start_time": 1785628800,
                    "speakers": [{"speaker_name": "Steve"}],
                    "pubsub_jwt": "must-not-leak",
                },
                {
                    "otid": "outside",
                    "title": "Outside range",
                    "start_time": 1785542399,
                },
            ],
            "end_of_list": False,
            "last_load_ts": 1785500000,
        }
    )

    result = service.list_speeches(
        page_size=20, cursor="1785700000", start_date=date(2026, 8, 2)
    )

    client.get_speeches.assert_called_once_with(
        folder=0,
        page_size=20,
        source="owned",
        last_load_ts=1785700000,
    )
    assert [item["id"] for item in result["speeches"]] == ["inside"]
    assert result["speeches"][0]["speakers"] == ["Steve"]
    assert result["next_cursor"] == "1785500000"


def test_list_speeches_supports_exact_folder(service, client):
    client.list_folder_speeches.return_value = response(
        {"speeches": [], "end_of_list": True, "last_load_speech_id": "last"}
    )

    result = service.list_speeches(folder="2_work", cursor="previous")

    client.list_folder_speeches.assert_called_once_with(
        2,
        page_size=25,
        last_load_speech_id="previous",
        speech_metadata=True,
    )
    assert result["folder"] == {"id": 2, "name": "2_work"}
    assert result["complete"] is True


def test_search_speeches_normalizes_and_filters_hits(service, client):
    client.search_speeches.return_value = response(
        {
            "hits": [
                {
                    "speech_otid": "speech-1",
                    "title": "Codex review",
                    "folder_id": 2,
                    "start_time": 1785628800,
                    "duration": 60,
                    "speaker": ["Steve"],
                    "matched_transcripts": [
                        {
                            "matched_speaker_name": "Steve",
                            "start_offset": 1_600,
                            "matched_transcript": "We used Codex.",
                        }
                    ],
                    "sparse_rerank_text": "must-not-leak",
                }
            ],
            "scroll_id": "next-page",
        }
    )

    result = service.search_speeches("Codex", page_size=1, folder="2_work")

    client.search_speeches.assert_called_once_with("Codex", size=1, scroll_id=None)
    assert result["hits"][0]["id"] == "speech-1"
    assert result["hits"][0]["matches"][0]["speaker"] == "Steve"
    assert result["hits"][0]["matches"][0]["start_ms"] == 100
    assert "sparse_rerank_text" not in result["hits"][0]
    assert result["next_cursor"] == "next-page"


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
        {"speaker": "Steve", "start_ms": 1, "end_ms": 1, "text": "Hello"}
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


def test_get_speeches_accepts_otter_url(service, client):
    client.get_speech.return_value = response(
        {"speech": {"otid": "speech-1", "title": "Call"}}
    )

    service.get_speeches(
        ["https://otter.ai/u/speech-1?tab=chat&view=transcript"],
        include_transcript=False,
    )

    client.get_speech.assert_called_once_with("speech-1")


def test_get_speeches_rejects_non_otter_url(service):
    with pytest.raises(ValueError, match="unsupported Otter URL"):
        service.get_speeches(["https://example.com/u/speech-1"])


def test_export_speeches_markdown_preserves_normalized_payload(
    service, client, tmp_path
):
    client.get_speech.return_value = response(
        {
            "speech": {
                "otid": "speech-1",
                "title": "Emma / Steve 1:1",
                "start_time": 1785628800,
                "speakers": [{"id": 7, "speaker_name": "Steve"}],
                "transcripts": [
                    {
                        "speaker_id": 7,
                        "start_offset": 16_000,
                        "end_offset": 32_000,
                        "transcript": "Line one\nLine two",
                    }
                ],
            }
        }
    )

    result = service.export_speeches_markdown(["speech-1"], str(tmp_path))

    path = tmp_path / "2026-08-02_emma-steve-1-1_speech-1.md"
    assert result["files"][0]["path"] == str(path)
    content = path.read_text()
    assert '"speaker": "Steve"' in content
    assert '"text": "Line one\\nLine two"' in content
    assert result["files"][0]["transcript_segments"] == 1


def test_normalization_converts_otter_ticks_to_milliseconds(service, client):
    client.get_speech.return_value = response(
        {
            "speech": {
                "otid": "speech-1",
                "speech_outline": [
                    {"text": "Topic", "start_offset": 16_000, "end_offset": 32_000}
                ],
                "transcripts": [
                    {
                        "start_offset": 1_600,
                        "end_offset": 3_200,
                        "transcript": "Hello",
                    }
                ],
            }
        }
    )

    result = service.get_speeches(["speech-1"])[0]

    assert result["outline"][0]["start_ms"] == 1_000
    assert result["outline"][0]["end_ms"] == 2_000
    assert result["transcript"][0]["start_ms"] == 100
    assert result["transcript"][0]["end_ms"] == 200


def test_export_speeches_markdown_rejects_relative_path(service):
    with pytest.raises(ValueError, match="absolute path"):
        service.export_speeches_markdown(["speech-1"], "relative")


def test_export_speeches_markdown_refuses_overwrite(service, client, tmp_path):
    client.get_speech.return_value = response(
        {"speech": {"otid": "speech-1", "title": "Call"}}
    )
    service.export_speeches_markdown(["speech-1"], str(tmp_path))

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        service.export_speeches_markdown(["speech-1"], str(tmp_path))


def test_move_preview_does_not_mutate(service, client):
    client.get_speech.return_value = response(
        {"speech": {"otid": "speech-1", "title": "Call", "folder": None}}
    )

    result = service.move_speeches(["speech-1"], "2_work", confirm=False)

    assert result["confirmed"] is False
    client.move_speeches_to_folder.assert_not_called()


def test_move_uses_library_and_verifies(service, client):
    client.get_speech.side_effect = [
        response({"speech": {"otid": "speech-1", "title": "Call", "folder": None}}),
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
