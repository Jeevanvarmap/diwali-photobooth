"""Three-shot session: 10-second countdown, cutouts, optional AI, Drive."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cv2

from app import ai_scene, drive
from app.camera import Camera
from app.compose import render_shot
from app.config import COUNTDOWN_SECONDS, OUTPUT_DIR, PHOTO_COUNT, ai_available

log = logging.getLogger(__name__)


@dataclass
class Session:
    id: str
    day: str
    directory: Path
    ai_enabled: bool
    status: str = "countdown"
    shot: int = 1
    shots_taken: int = 0
    countdown_ends_at: float | None = None
    results: list[dict] = field(default_factory=list)
    ai_results: list[dict] = field(default_factory=list)
    ai_pending: bool = False
    ai_error: str = ""
    drive_url: str = ""
    drive_error: str = ""
    error: str = ""

    def public(self, now: float | None = None) -> dict:
        return {
            "active": True,
            "id": self.id,
            "day": self.day,
            "status": self.status,
            "shot": self.shot,
            "photo_count": PHOTO_COUNT,
            "shots_taken": self.shots_taken,
            "countdown_seconds": COUNTDOWN_SECONDS,
            "countdown_ends_at": self.countdown_ends_at,
            "server_now": now if now is not None else time.time(),
            "results": [_public_result(item) for item in self.results],
            "ai_results": [_public_result(item) for item in self.ai_results],
            "ai_pending": self.ai_pending,
            "ai_error": self.ai_error,
            "drive_url": self.drive_url,
            "drive_error": self.drive_error,
            "error": self.error,
        }


def _public_result(item: dict) -> dict:
    return {
        "shot": item["shot"],
        "plate_id": item["plate_id"],
        "label": item["label"],
        "url": item["url"],
    }


class Booth:
    def __init__(self, camera: Camera) -> None:
        self.camera = camera
        self._lock = threading.Lock()
        self._session: Session | None = None
        self._cancel = threading.Event()

    def state(self) -> dict:
        with self._lock:
            if self._session is None:
                return {"active": False}
            return self._session.public()

    def qr_bytes(self) -> bytes | None:
        with self._lock:
            url = self._session.drive_url if self._session else ""
        if not url:
            return None
        return drive.qr_png(url)

    def start(self, use_ai: bool) -> dict:
        with self._lock:
            if self._session and self._session.status in {"countdown", "processing"}:
                raise RuntimeError("A session is already running.")
            now = datetime.now()
            day = now.strftime("%Y-%m-%d")
            session_id = now.strftime("%H%M%S") + "-" + uuid.uuid4().hex[:4]
            directory = OUTPUT_DIR / day / session_id
            directory.mkdir(parents=True, exist_ok=True)
            session = Session(
                id=session_id,
                day=day,
                directory=directory,
                ai_enabled=bool(use_ai) and ai_available(),
            )
            self._session = session
            self._cancel.clear()
        threading.Thread(target=self._run, args=(session,), name="booth", daemon=True).start()
        return session.public()

    def reset(self) -> dict:
        self._cancel.set()
        with self._lock:
            self._session = None
        return {"active": False}

    def _run(self, session: Session) -> None:
        try:
            for shot in range(1, PHOTO_COUNT + 1):
                ends = time.time() + COUNTDOWN_SECONDS
                if not self._update(session, status="countdown", shot=shot, countdown_ends_at=ends):
                    return
                if not self._sleep_until(ends):
                    return
                frame = self.camera.snapshot()
                if frame is None:
                    self._fail(session, "The camera did not return a photo.")
                    return
                path = session.directory / f"original-{shot}.jpg"
                if not cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92]):
                    self._fail(session, "Could not save the photo.")
                    return
                if not self._update(session, shots_taken=shot):
                    return

            if not self._update(session, status="processing", countdown_ends_at=None):
                return

            results: list[dict] = []
            for shot in range(1, PHOTO_COUNT + 1):
                if self._cancel.is_set():
                    return
                rendered = render_shot(session.directory / f"original-{shot}.jpg", session.directory, shot)
                for item in rendered:
                    item["url"] = f"/media/{session.day}/{session.id}/{item['filename']}"
                results.extend(rendered)
                if not self._update(session, results=list(results)):
                    return

            if not self._update(session, status="ready"):
                return

            self._upload(session, [item["filename"] for item in session.results])

            if session.ai_enabled:
                self._run_ai(session)
                self._upload(session, [item["filename"] for item in session.ai_results], share=False)
        except Exception as exc:
            log.exception("Session failed")
            self._fail(session, "Something went wrong while making the photos.")
            log.error("%s", exc)

    def _run_ai(self, session: Session) -> None:
        if not self._update(session, ai_pending=True, ai_error=""):
            return
        made: list[dict] = []
        for shot in range(1, PHOTO_COUNT + 1):
            if self._cancel.is_set():
                return
            filename = f"ai-{shot}.jpg"
            dest = session.directory / filename
            try:
                ai_scene.generate(session.directory / f"original-{shot}.jpg", dest, shot)
            except Exception as exc:
                log.exception("AI scene failed for shot %s", shot)
                self._update(session, ai_error=str(exc) or "The AI scene could not be made.")
                break
            item = {
                "shot": shot,
                "plate_id": "ai",
                "label": "AI Diwali scene",
                "filename": filename,
                "url": f"/media/{session.day}/{session.id}/{filename}",
            }
            made.append(item)
            if not self._update(session, ai_results=list(made)):
                return
        self._update(session, ai_pending=False)

    def _upload(self, session: Session, names: list[str], share: bool = True) -> None:
        if self._cancel.is_set() or not names:
            return
        if not drive.configured():
            self._update(
                session,
                drive_error="Saved on this Mac. Add credentials.json to upload to Google Drive.",
            )
            return
        try:
            url, warning = drive.upload_session(
                session.directory,
                session.day,
                session.id,
                names,
                share=share,
            )
        except Exception as exc:
            log.exception("Drive upload failed")
            self._update(session, drive_error=str(exc) or "Could not upload to Google Drive.")
            return
        changes = {"drive_url": url}
        if warning or share:
            changes["drive_error"] = warning
        self._update(session, **changes)

    def _sleep_until(self, deadline: float) -> bool:
        while time.time() < deadline:
            if self._cancel.is_set():
                return False
            time.sleep(0.05)
        return not self._cancel.is_set()

    def _update(self, session: Session, **changes) -> bool:
        with self._lock:
            if self._session is not session or self._cancel.is_set():
                return False
            for key, value in changes.items():
                setattr(session, key, value)
            return True

    def _fail(self, session: Session, message: str) -> None:
        with self._lock:
            if self._session is not session:
                return
            session.status = "error"
            session.error = message
            session.countdown_ends_at = None
            session.ai_pending = False
