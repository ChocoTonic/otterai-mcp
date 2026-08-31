"""Safe, normalized operations backed only by otterai-py."""

from __future__ import annotations

import threading
from typing import Any

from otterai import OtterAI

from .settings import Settings


class OtterService:
    def __init__(self, settings: Settings, client: OtterAI | None = None):
        self.settings = settings
        self.client = client or OtterAI()
        self._authenticated = client is not None
        self._lock = threading.RLock()

    def _login(self) -> None:
        if self._authenticated:
            return
        response = self.client.login(self.settings.username, self.settings.password)
        self._data(response, "login")
        self._authenticated = True

    @staticmethod
    def _data(response: dict[str, Any], operation: str) -> Any:
        status = response.get("status")
        if status != 200 and str(status).lower() != "ok":
            raise RuntimeError(f"Otter {operation} failed with status {status}")
        return response.get("data", {})

    def list_folders(self) -> list[dict[str, Any]]:
        with self._lock:
            self._login()
            data = self._data(self.client.get_folders(), "folder listing")
        folders = data.get("folders", []) if isinstance(data, dict) else []
        return sorted(
            (
                {
                    "id": folder.get("id"),
                    "name": folder.get("folder_name"),
                    "speech_count": folder.get("speech_count", 0),
                }
                for folder in folders
            ),
            key=lambda folder: str(folder["name"]),
        )

    def list_unsorted(
        self, page_size: int = 25, cursor: int | None = None
    ) -> dict[str, Any]:
        with self._lock:
            self._login()
            data = self._data(
                self.client.list_unsorted_speeches(
                    page_size=page_size, last_load_ts=cursor
                ),
                "unsorted speech listing",
            )
        speeches = data.get("speeches", []) if isinstance(data, dict) else []
        end_of_list = bool(data.get("end_of_list", True))
        return {
            "speeches": [self._speech_summary(speech) for speech in speeches],
            "next_cursor": None if end_of_list else data.get("last_load_ts"),
            "complete": end_of_list,
        }

    def get_speeches(
        self, speech_ids: list[str], include_transcript: bool = True
    ) -> list[dict[str, Any]]:
        results = []
        with self._lock:
            self._login()
            for speech_id in speech_ids:
                data = self._data(
                    self.client.get_speech(speech_id), f"speech fetch for {speech_id}"
                )
                speech = data.get("speech", data) if isinstance(data, dict) else {}
                results.append(self._speech_detail(speech, include_transcript))
        return results

    def move_speeches(
        self, speech_ids: list[str], destination: str, confirm: bool
    ) -> dict[str, Any]:
        folders = self.list_folders()
        destination_folder = self._resolve_folder(destination, folders)
        destination_identity = {
            "id": destination_folder["id"],
            "name": destination_folder["name"],
        }
        before = self.get_speeches(speech_ids, include_transcript=False)
        plan = [
            {
                "id": speech["id"],
                "title": speech["title"],
                "from": speech["folder"],
                "to": destination_identity,
            }
            for speech in before
        ]
        pending_ids = [
            speech["id"]
            for speech in before
            if not speech["folder"]
            or speech["folder"].get("id") != destination_folder["id"]
        ]
        if not confirm:
            return {"confirmed": False, "changed": False, "plan": plan}
        if pending_ids:
            with self._lock:
                self._login()
                self._data(
                    self.client.move_speeches_to_folder(
                        destination_folder["id"], pending_ids
                    ),
                    "speech move",
                )
        after = self.get_speeches(speech_ids, include_transcript=False)
        failures = [
            speech
            for speech in after
            if not speech["folder"]
            or speech["folder"].get("id") != destination_folder["id"]
        ]
        if failures:
            failed_ids = ", ".join(speech["id"] for speech in failures)
            raise RuntimeError(f"move verification failed for: {failed_ids}")
        return {
            "confirmed": True,
            "changed": bool(pending_ids),
            "destination": destination_identity,
            "speeches": after,
        }

    @staticmethod
    def _resolve_folder(
        destination: str, folders: list[dict[str, Any]]
    ) -> dict[str, Any]:
        value = str(destination).strip()
        matches = [
            folder
            for folder in folders
            if value == str(folder["id"]) or value == folder["name"]
        ]
        if len(matches) != 1:
            names = ", ".join(str(folder["name"]) for folder in folders)
            raise ValueError(
                f"unknown destination folder {value!r}; choose from: {names}"
            )
        return matches[0]

    @classmethod
    def _speech_detail(
        cls, speech: dict[str, Any], include_transcript: bool
    ) -> dict[str, Any]:
        result = cls._speech_summary(speech)
        result["summary"] = speech.get("short_abstract_summary") or speech.get(
            "summary"
        )
        result["outline"] = cls._normalize_outline(
            speech.get("speech_outline") or []
        )
        if include_transcript:
            result["transcript"] = cls._normalize_transcript(speech)
        return result

    @staticmethod
    def _speech_summary(speech: dict[str, Any]) -> dict[str, Any]:
        folder = speech.get("folder") or None
        safe_folder = (
            {"id": folder.get("id"), "name": folder.get("folder_name")}
            if folder
            else None
        )
        return {
            "id": speech.get("otid") or speech.get("id"),
            "title": speech.get("title") or "Untitled",
            "start_time": speech.get("start_time"),
            "duration_seconds": speech.get("duration"),
            "folder": safe_folder,
            "url": (
                f"https://otter.ai/u/{speech.get('otid')}"
                if speech.get("otid")
                else None
            ),
        }

    @staticmethod
    def _normalize_outline(outline: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "title": item.get("text"),
                "start_ms": item.get("start_offset"),
                "end_ms": item.get("end_offset"),
            }
            for item in outline
        ]

    @staticmethod
    def _normalize_transcript(speech: dict[str, Any]) -> list[dict[str, Any]]:
        speakers = {
            speaker.get("id"): speaker.get("speaker_name")
            for speaker in speech.get("speakers", [])
        }
        return [
            {
                "speaker": speakers.get(segment.get("speaker_id"))
                or f"Speaker {segment.get('label', '?')}",
                "start_ms": segment.get("start_offset"),
                "end_ms": segment.get("end_offset"),
                "text": segment.get("transcript", ""),
            }
            for segment in (speech.get("transcripts") or [])
        ]
