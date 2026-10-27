"""One OpenCV capture shared by the preview stream and the shutter."""

from __future__ import annotations

import json
import logging
import platform
import subprocess
import threading
import time

import cv2
import numpy as np

from app.config import OUTPUT_HEIGHT, OUTPUT_WIDTH

log = logging.getLogger(__name__)

BACKEND = cv2.CAP_AVFOUNDATION if platform.system() == "Darwin" else cv2.CAP_ANY


class Camera:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._jpeg: bytes | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._reopen = threading.Event()
        self._cameras: list[dict] = []
        self._index = 0
        self._open = False
        self._error = ""

    def start(self) -> None:
        self.refresh_devices()
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def refresh_devices(self) -> list[dict]:
        names = _device_names()
        if not names:
            names = ["Camera 0"]
        cameras = [{"index": i, "name": name} for i, name in enumerate(names)]
        with self._lock:
            if self._cameras and any(item["index"] == self._index for item in cameras):
                selected = self._index
            else:
                selected = _preferred_index(cameras)
            self._cameras = cameras
            self._index = selected
            self._reopen.set()
        return cameras

    def select(self, index: int) -> None:
        with self._lock:
            self._index = index
            self._reopen.set()

    def status(self) -> dict:
        with self._lock:
            return {
                "cameras": list(self._cameras),
                "selected": self._index,
                "open": self._open,
                "error": self._error,
            }

    def snapshot(self) -> np.ndarray | None:
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.copy()

    def preview_jpeg(self) -> bytes | None:
        with self._lock:
            return self._jpeg

    def _loop(self) -> None:
        cap = None
        opened_index = None
        while self._running:
            with self._lock:
                wanted = self._index
                reopen = self._reopen.is_set()
                if reopen:
                    self._reopen.clear()
            if cap is None or opened_index != wanted or reopen:
                if cap is not None:
                    cap.release()
                    cap = None
                cap = cv2.VideoCapture(wanted, BACKEND)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                opened_index = wanted
                ok = cap.isOpened()
                with self._lock:
                    self._open = ok
                    self._error = "" if ok else "Could not open the camera."
                    if not ok:
                        self._frame = None
                        self._jpeg = None
                if not ok:
                    cap.release()
                    cap = None
                    time.sleep(1.5)
                    continue
                for _ in range(6):
                    cap.read()
            ok, frame = cap.read()
            if not ok or frame is None:
                with self._lock:
                    self._open = False
                    self._error = "The camera stopped sending video."
                time.sleep(0.1)
                cap.release()
                cap = None
                continue
            portrait = _portrait(cv2.flip(frame, 1))
            encoded, buf = cv2.imencode(
                ".jpg",
                portrait,
                [int(cv2.IMWRITE_JPEG_QUALITY), 80],
            )
            with self._lock:
                self._open = True
                self._error = ""
                self._frame = portrait
                self._jpeg = buf.tobytes() if encoded else None
        if cap is not None:
            cap.release()


def _device_names() -> list[str]:
    if platform.system() != "Darwin":
        return []
    try:
        raw = subprocess.check_output(
            ["system_profiler", "SPCameraDataType", "-json"],
            text=True,
            timeout=8,
        )
        data = json.loads(raw)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
        log.warning("Could not list cameras: %s", exc)
        return []
    names = []
    for item in data.get("SPCameraDataType", []):
        name = str(item.get("_name") or "").strip()
        if name:
            names.append(name)
    return names


def _preferred_index(cameras: list[dict]) -> int:
    def score(name: str) -> int:
        lowered = name.lower()
        if "dji" in lowered or "osmo" in lowered or "action" in lowered:
            return 0
        if lowered.strip() in {"uvc camera", "usb camera"} or lowered.startswith("uvc "):
            return 1
        if "iphone" in lowered or "continuity" in lowered:
            return 3
        return 2

    ranked = sorted(cameras, key=lambda item: (score(item["name"]), item["index"]))
    return ranked[0]["index"] if ranked else 0


def _portrait(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    target = OUTPUT_WIDTH / OUTPUT_HEIGHT
    current = width / height if height else target
    if current > target:
        new_width = max(1, int(round(height * target)))
        x = max(0, (width - new_width) // 2)
        frame = frame[:, x : x + new_width]
    else:
        new_height = max(1, int(round(width / target)))
        y = max(0, (height - new_height) // 2)
        frame = frame[y : y + new_height, :]
    return cv2.resize(frame, (OUTPUT_WIDTH, OUTPUT_HEIGHT), interpolation=cv2.INTER_AREA)
