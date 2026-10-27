"""Optional Diwali scene that keeps the photographed person and clothes."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx
from PIL import Image

from app.config import (
    AI_PROVIDER,
    GEMINI_API_KEY,
    GEMINI_IMAGE_MODEL,
    OPENAI_API_KEY,
    OPENAI_IMAGE_MODEL,
)

log = logging.getLogger(__name__)

_SCENES = (
    "a night courtyard of clay diyas and marigold garlands, with warm golden light",
    "a courtyard floor covered by a colorful rangoli and strings of warm fairy lights",
    "a festive night with soft fireworks above an old haveli courtyard",
)

_INSTRUCTION = (
    "Edit this photograph. Keep every person exactly as photographed: the same faces, "
    "bodies, pose, jewelry, and traditional clothing. Do not change their identity, "
    "outfit, or pose, and do not add extra people. Replace only the background with {scene}. "
    "Photorealistic portrait, full body visible."
)


def generate(original_path: Path, dest_path: Path, shot: int) -> None:
    scene = _SCENES[(shot - 1) % len(_SCENES)]
    prompt = _INSTRUCTION.format(scene=scene)
    if AI_PROVIDER == "gemini":
        png = _gemini(original_path, prompt)
    elif AI_PROVIDER == "openai":
        png = _openai(original_path, prompt)
    else:
        raise RuntimeError(f"Unknown AI_PROVIDER '{AI_PROVIDER}'. Use openai or gemini.")
    image = Image.open(__import__("io").BytesIO(png)).convert("RGB")
    image = image.resize((1080, 1350), Image.Resampling.LANCZOS)
    image.save(dest_path, quality=92)


def _prepared_jpeg(path: Path, limit: int = 1280) -> bytes:
    import io

    image = Image.open(path).convert("RGB")
    image.thumbnail((limit, limit), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def _openai(path: Path, prompt: str) -> bytes:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    jpeg = _prepared_jpeg(path)
    response = httpx.post(
        "https://api.openai.com/v1/images/edits",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        files={"image": ("photo.jpg", jpeg, "image/jpeg")},
        data={
            "model": OPENAI_IMAGE_MODEL,
            "prompt": prompt,
            "size": "1024x1536",
            "quality": "high",
        },
        timeout=180,
    )
    if response.status_code >= 400:
        raise RuntimeError(_api_error("OpenAI", response))
    payload = response.json()
    data = (payload.get("data") or [{}])[0]
    if data.get("b64_json"):
        return base64.b64decode(data["b64_json"])
    if data.get("url"):
        image = httpx.get(data["url"], timeout=60)
        image.raise_for_status()
        return image.content
    raise RuntimeError("OpenAI did not return an image.")


def _gemini(path: Path, prompt: str) -> bytes:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    jpeg = _prepared_jpeg(path)
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_IMAGE_MODEL}:generateContent"
    )
    response = httpx.post(
        url,
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        json={
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": base64.b64encode(jpeg).decode("ascii"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        },
        timeout=180,
    )
    if response.status_code >= 400:
        raise RuntimeError(_api_error("Gemini", response))
    payload = response.json()
    for candidate in payload.get("candidates") or []:
        for part in (candidate.get("content") or {}).get("parts") or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    raise RuntimeError("Gemini did not return an image.")


def _api_error(name: str, response: httpx.Response) -> str:
    detail = response.text[:300].replace("\n", " ")
    log.warning("%s image edit failed: %s %s", name, response.status_code, detail)
    return f"{name} could not make a scene ({response.status_code})."
