"""Cut guests out and place them on the Diwali plates."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from app.plates import load_plates

log = logging.getLogger(__name__)

_session = None
_session_lock = threading.Lock()


def get_session():
    global _session
    with _session_lock:
        if _session is None:
            from rembg import new_session

            model = _installed_model()
            log.info("Loading background removal model %s", model)
            _session = new_session(model)
        return _session


def _installed_model() -> str:
    path = _model_file()
    if path is None:
        raise RuntimeError("Background model is not downloaded.")
    return "u2net" if path.name == "u2net.onnx" else "u2netp"


def _model_file() -> Path | None:
    root = Path.home() / ".rembg" / "models"
    full = root / "u2net" / "u2net.onnx"
    small = root / "u2netp" / "u2netp.onnx"
    if full.is_file() and full.stat().st_size > 100_000_000:
        return full
    if small.is_file() and small.stat().st_size > 1_000_000:
        return small
    return None


def preload() -> None:
    if _model_file() is None:
        log.info("No rembg model on disk yet; cutouts will use the local fallback until it is downloaded")
        return
    get_session()


def render_shot(original_path: Path, dest_dir: Path, shot: int) -> list[dict]:
    image = Image.open(original_path).convert("RGB")
    cutout = _cutout(image)
    results = []
    for plate_id, label, plate in load_plates():
        composed = _place(plate, cutout)
        filename = f"{plate_id}-{shot}.jpg"
        composed.convert("RGB").save(dest_dir / filename, quality=92)
        results.append(
            {
                "shot": shot,
                "plate_id": plate_id,
                "label": label,
                "url": None,
                "filename": filename,
            }
        )
    return results


def _cutout(image: Image.Image) -> Image.Image:
    if _model_file() is not None:
        try:
            return _trim(_rembg_cutout(image))
        except Exception:
            log.exception("Background model failed; using the local cutout")
    return _trim(_grabcut(image))


def _rembg_cutout(image: Image.Image) -> Image.Image:
    from rembg import remove

    cut = remove(image, session=get_session())
    if cut.mode != "RGBA":
        cut = cut.convert("RGBA")
    return cut


def _grabcut(image: Image.Image) -> Image.Image:
    rgb = np.array(image.convert("RGB"))
    small = cv2.resize(rgb, (480, 600), interpolation=cv2.INTER_AREA)
    bgr = cv2.cvtColor(small, cv2.COLOR_RGB2BGR)
    height, width = bgr.shape[:2]
    mask = np.zeros((height, width), np.uint8)
    margin_x = int(width * 0.06)
    margin_y = int(height * 0.03)
    rect = (margin_x, margin_y, width - 2 * margin_x, height - 2 * margin_y)
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    cv2.grabCut(bgr, mask, rect, bgd, fgd, 3, cv2.GC_INIT_WITH_RECT)
    keep = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    keep = cv2.erode(keep, np.ones((3, 3), np.uint8), iterations=1)
    keep = cv2.resize(keep, (image.width, image.height), interpolation=cv2.INTER_LINEAR)
    rgba = image.convert("RGBA")
    rgba.putalpha(Image.fromarray(keep, mode="L"))
    return rgba


def _trim(cut: Image.Image) -> Image.Image:
    alpha = cut.getchannel("A")
    bbox = alpha.getbbox()
    if bbox:
        cut = cut.crop(bbox)
    red, green, blue, mask = cut.split()
    mask = mask.filter(ImageFilter.GaussianBlur(radius=0.8))
    return Image.merge("RGBA", (red, green, blue, mask))


def _place(plate: Image.Image, person: Image.Image) -> Image.Image:
    canvas = plate.convert("RGBA")
    width, height = canvas.size
    pw, ph = person.size
    if pw < 2 or ph < 2:
        return canvas
    scale = min((height * 0.86) / ph, (width * 0.92) / pw)
    resized = person.resize((max(1, int(pw * scale)), max(1, int(ph * scale))), Image.Resampling.LANCZOS)
    rw, rh = resized.size
    x = (width - rw) // 2
    y = height - rh - 36
    _shadow(canvas, x, y, rw, rh)
    canvas.alpha_composite(resized, (x, y))
    return canvas


def _shadow(canvas: Image.Image, x: int, y: int, rw: int, rh: int) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    ell_w = int(rw * 0.5)
    ell_h = max(12, int(rh * 0.045))
    ex = x + (rw - ell_w) // 2
    ey = y + rh - ell_h // 2
    draw.ellipse((ex, ey, ex + ell_w, ey + ell_h), fill=(0, 0, 0, 120))
    layer = layer.filter(ImageFilter.GaussianBlur(radius=14))
    canvas.alpha_composite(layer)
