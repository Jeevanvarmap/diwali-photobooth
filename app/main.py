"""Diwali photobooth server."""

from __future__ import annotations

import logging
import re
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.booth import Booth
from app.camera import Camera
from app.compose import preload
from app.config import (
    AI_PROVIDER,
    COUNTDOWN_SECONDS,
    HOLD_STILL_SECONDS,
    PHOTO_COUNT,
    STATIC_DIR,
    ai_available,
)
from app.drive import configured as drive_configured
from app.plates import ensure_backgrounds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

camera = Camera()
booth = Booth(camera)

_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_SESSION = re.compile(r"\d{6}-[0-9a-f]{4}")
_FILE = re.compile(r"(?:original|diyas|rangoli|fireworks|temple|ai)-[123]\.jpg")


class StartBody(BaseModel):
    ai: bool = False
    camera_index: int | None = None


class CameraBody(BaseModel):
    index: int


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_backgrounds()
    threading.Thread(target=_preload_model, name="rembg", daemon=True).start()
    camera.start()
    yield
    camera.stop()


def _preload_model() -> None:
    try:
        preload()
    except Exception:
        log.exception("Could not preload the background removal model")


app = FastAPI(title="Diwali Photobooth", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
def config() -> dict:
    return {
        "ai_available": ai_available(),
        "ai_provider": AI_PROVIDER,
        "photo_count": PHOTO_COUNT,
        "countdown_seconds": COUNTDOWN_SECONDS,
        "hold_still_seconds": HOLD_STILL_SECONDS,
        "drive_configured": drive_configured(),
    }


@app.get("/api/cameras")
def cameras() -> dict:
    return camera.status()


@app.post("/api/cameras/refresh")
def refresh_cameras() -> dict:
    _reject_if_busy()
    camera.refresh_devices()
    return camera.status()


@app.post("/api/camera")
def select_camera(body: CameraBody) -> dict:
    _reject_if_busy()
    camera.select(body.index)
    return camera.status()


@app.get("/api/preview.mjpeg")
def preview() -> StreamingResponse:
    return StreamingResponse(_preview_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/session")
def session() -> dict:
    return booth.state()


@app.post("/api/session")
def start_session(body: StartBody) -> dict:
    if body.camera_index is not None:
        camera.select(body.camera_index)
    try:
        return booth.start(body.ai)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/session/reset")
def reset_session() -> dict:
    return booth.reset()


@app.get("/api/session/qr.png")
def session_qr() -> Response:
    png = booth.qr_bytes()
    if not png:
        raise HTTPException(status_code=404, detail="No Drive link yet.")
    return Response(content=png, media_type="image/png")


@app.get("/media/{day}/{session_id}/{filename}")
def media(day: str, session_id: str, filename: str) -> FileResponse:
    if not (_DAY.fullmatch(day) and _SESSION.fullmatch(session_id) and _FILE.fullmatch(filename)):
        raise HTTPException(status_code=404)
    from app.config import OUTPUT_DIR

    path = OUTPUT_DIR / day / session_id / filename
    if not path.is_file():
        raise HTTPException(status_code=404)
    media_type = "image/jpeg"
    return FileResponse(path, media_type=media_type)


def _preview_frames():
    while True:
        frame = camera.preview_jpeg()
        if frame:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        time.sleep(0.05)


def _reject_if_busy() -> None:
    status = booth.state().get("status")
    if status in {"countdown", "processing"}:
        raise HTTPException(status_code=409, detail="Wait until this guest is finished.")
