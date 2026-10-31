"""Safe, normalized operations backed only by otterai-py."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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
        self,
        page_size: int = 25,
        cursor: int | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        self._validate_dates(start_date, end_date)
        with self._lock:
            self._login()
            data = self._data(
                self.client.list_unsorted_speeches(
                    page_size=page_size, last_load_ts=cursor
                ),
                "unsorted speech listing",
            )
        speeches = data.get("speeches", []) if isinstance(data, dict) else []
        filtered = [
            speech
            for speech in speeches
            if self._within_dates(speech.get("start_time"), start_date, end_date)
        ]
        end_of_list = bool(data.get("end_of_list", True))
        return {
            "speeches": [self._speech_summary(speech) for speech in filtered],
            "next_cursor": None if end_of_list else data.get("last_load_ts"),
            "complete": end_of_list,
        }

    def list_speeches(
        self,
        folder: str | None = None,
        page_size: int = 25,
        cursor: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        self._validate_dates(start_date, end_date)
        destination = None
        with self._lock:
            self._login()
            if folder is None:
                numeric_cursor = int(cursor) if cursor is not None else None
                data = self._data(
                    self.client.get_speeches(
                        folder=0,
                        page_size=page_size,
                        source="owned",
                        last_load_ts=numeric_cursor,
                    ),
                    "speech listing",
                )
                next_cursor = data.get("last_load_ts")
            else:
                destination = self._resolve_folder(folder, self.list_folders())
                data = self._data(
                    self.client.list_folder_speeches(
                        destination["id"],
                        page_size=page_size,
                        last_load_speech_id=cursor,
                        speech_metadata=True,
                    ),
                    "folder speech listing",
                )
                next_cursor = data.get("last_load_speech_id")

        speeches = data.get("speeches", []) if isinstance(data, dict) else []
        filtered = [
            speech
            for speech in speeches
            if self._within_dates(speech.get("start_time"), start_date, end_date)
        ]
        complete = bool(data.get("end_of_list", True))
        return {
            "speeches": [self._speech_listing(speech) for speech in filtered],
            "folder": (
                {"id": destination["id"], "name": destination["name"]}
                if destination
                else None
            ),
            "next_cursor": None if complete else str(next_cursor),
            "complete": complete,
        }

    def search_speeches(
        self,
        query: str,
        page_size: int = 25,
        cursor: str | None = None,
        folder: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        self._validate_dates(start_date, end_date)
        folders = self.list_folders()
        folder_by_id = {str(item["id"]): item for item in folders}
        destination = self._resolve_folder(folder, folders) if folder else None
        with self._lock:
            self._login()
            data = self._data(
                self.client.search_speeches(query, size=page_size, scroll_id=cursor),
                "speech search",
            )

        hits = data.get("hits", []) if isinstance(data, dict) else []
        filtered = [
            hit
            for hit in hits
            if (
                destination is None
                or str(hit.get("folder_id")) == str(destination["id"])
            )
            and self._within_dates(hit.get("start_time"), start_date, end_date)
        ]
        complete = len(hits) < page_size
        return {
            "hits": [self._search_hit(hit, folder_by_id) for hit in filtered],
            "next_cursor": None if complete else data.get("scroll_id"),
            "complete": complete,
        }

    def get_speeches(
        self, speech_ids: list[str], include_transcript: bool = True
    ) -> list[dict[str, Any]]:
        results = []
        with self._lock:
            self._login()
            for speech_id in speech_ids:
                speech_id = self._speech_id(speech_id)
                data = self._data(
                    self.client.get_speech(speech_id), f"speech fetch for {speech_id}"
                )
                speech = data.get("speech", data) if isinstance(data, dict) else {}
                results.append(self._speech_detail(speech, include_transcript))
        return results

    def export_speeches_markdown(
        self,
        speech_ids: list[str],
        output_directory: str,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Export normalized speeches as lossless JSON embedded in Markdown."""
        destination = Path(output_directory)
        if not destination.is_absolute():
            raise ValueError("output_directory must be an absolute path")
        destination = destination.resolve()

        speeches = self.get_speeches(speech_ids, include_transcript=True)
        exports = [
            (speech, destination / self._markdown_filename(speech))
            for speech in speeches
        ]
        collisions = [path for _, path in exports if path.exists()]
        if collisions and not overwrite:
            paths = ", ".join(str(path) for path in collisions)
            raise FileExistsError(f"refusing to overwrite existing exports: {paths}")

        destination.mkdir(parents=True, exist_ok=True)
        written = []
        for speech, path in exports:
            payload = (
                "# Otter transcript export\n\n"
                "The fenced JSON below preserves every normalized metadata, outline, "
                "and transcript field returned by `otter_get_speeches`.\n\n"
                "```json\n"
                f"{json.dumps(speech, ensure_ascii=False, indent=2)}\n"
                "```\n"
            )
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=destination,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(payload)
                temporary_path = Path(handle.name)
            os.replace(temporary_path, path)
            written.append(
                {
                    "id": speech["id"],
                    "title": speech["title"],
                    "path": str(path),
                    "transcript_segments": len(speech.get("transcript") or []),
                }
            )
        return {"format": "markdown+json", "files": written}

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
        result["outline"] = cls._normalize_outline(speech.get("speech_outline") or [])
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

    @classmethod
    def _speech_listing(cls, speech: dict[str, Any]) -> dict[str, Any]:
        result = cls._speech_summary(speech)
        result["summary"] = speech.get("short_abstract_summary") or speech.get(
            "summary"
        )
        result["speakers"] = [
            speaker.get("speaker_name")
            for speaker in (speech.get("speakers") or [])
            if speaker.get("speaker_name")
        ]
        return result

    @staticmethod
    def _search_hit(
        hit: dict[str, Any], folder_by_id: dict[Any, dict[str, Any]]
    ) -> dict[str, Any]:
        speech_id = hit.get("speech_otid")
        folder = folder_by_id.get(str(hit.get("folder_id")))
        return {
            "id": speech_id,
            "title": hit.get("title") or "Untitled",
            "start_time": hit.get("start_time"),
            "duration_seconds": hit.get("duration"),
            "folder": (
                {"id": folder["id"], "name": folder["name"]} if folder else None
            ),
            "speakers": hit.get("speaker") or [],
            "matches": [
                {
                    "speaker": match.get("matched_speaker_name")
                    or match.get("speaker_name"),
                    "start_ms": match.get("start_offset"),
                    "text": match.get("matched_transcript", ""),
                }
                for match in (hit.get("matched_transcripts") or [])
            ],
            "url": f"https://otter.ai/u/{speech_id}" if speech_id else None,
        }

    @staticmethod
    def _within_dates(
        timestamp: Any, start_date: date | None, end_date: date | None
    ) -> bool:
        if timestamp is None:
            return start_date is None and end_date is None
        value = int(timestamp)
        if start_date is not None:
            start = int(datetime.combine(start_date, time.min, UTC).timestamp())
            if value < start:
                return False
        if end_date is not None:
            end = int(datetime.combine(end_date, time.max, UTC).timestamp())
            if value > end:
                return False
        return True

    @staticmethod
    def _validate_dates(start_date: date | None, end_date: date | None) -> None:
        if start_date is not None and end_date is not None and start_date > end_date:
            raise ValueError("start_date must be on or before end_date")

    @staticmethod
    def _speech_id(value: str) -> str:
        candidate = str(value).strip()
        parsed = urlparse(candidate)
        if parsed.scheme or parsed.netloc:
            if parsed.scheme != "https" or parsed.netloc.lower() != "otter.ai":
                raise ValueError(f"unsupported Otter URL: {candidate!r}")
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) != 2 or parts[0] != "u":
                raise ValueError(f"unsupported Otter URL: {candidate!r}")
            candidate = parts[1]
        if not candidate or "/" in candidate:
            raise ValueError(f"invalid speech ID: {candidate!r}")
        return candidate

    @staticmethod
    def _markdown_filename(speech: dict[str, Any]) -> str:
        timestamp = speech.get("start_time")
        day = (
            datetime.fromtimestamp(int(timestamp), UTC).date().isoformat()
            if timestamp is not None
            else "unknown-date"
        )
        title = re.sub(r"[^a-z0-9]+", "-", str(speech.get("title", "untitled")).lower())
        title = title.strip("-")[:80] or "untitled"
        speech_id = re.sub(r"[^A-Za-z0-9_-]+", "-", str(speech.get("id", "unknown")))
        return f"{day}_{title}_{speech_id}.md"

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

