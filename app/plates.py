"""Portrait Diwali backdrops, drawn so the center stays clear for a cutout."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from app.config import BACKGROUNDS_DIR, OUTPUT_HEIGHT, OUTPUT_WIDTH

PLATES = (
    ("diyas", "Diyas & marigolds"),
    ("rangoli", "Rangoli courtyard"),
    ("fireworks", "Fireworks haveli"),
    ("temple", "Temple lights"),
)

W = OUTPUT_WIDTH
H = OUTPUT_HEIGHT


def ensure_backgrounds() -> None:
    BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    builders = {
        "diyas": _diyas,
        "rangoli": _rangoli,
        "fireworks": _fireworks,
        "temple": _temple,
    }
    for plate_id, _label in PLATES:
        path = BACKGROUNDS_DIR / f"{plate_id}.jpg"
        if path.exists() and path.stat().st_size > 0:
            continue
        image = builders[plate_id]()
        image.convert("RGB").save(path, quality=92)


def load_plates() -> list[tuple[str, str, Image.Image]]:
    ensure_backgrounds()
    loaded = []
    for plate_id, label in PLATES:
        image = Image.open(BACKGROUNDS_DIR / f"{plate_id}.jpg").convert("RGB")
        image = image.resize((W, H), Image.Resampling.LANCZOS)
        loaded.append((plate_id, label, image))
    return loaded


def _canvas(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> np.ndarray:
    ramp = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    color_top = np.array(top, dtype=np.float32)
    color_bottom = np.array(bottom, dtype=np.float32)
    column = color_top * (1 - ramp) + color_bottom * ramp
    return np.broadcast_to(column, (H, W, 3)).copy()


def _add_glow(base: np.ndarray, points: list[tuple[float, float, float, tuple[int, int, int]]]) -> np.ndarray:
    """points: x, y, radius, rgb. Additive soft lights."""
    glow = np.zeros_like(base)
    yy, xx = np.mgrid[0:H, 0:W]
    for x, y, radius, rgb in points:
        strength = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * radius * radius))
        color = np.array(rgb, dtype=np.float32)
        glow += strength[..., None] * color * 0.45
    return np.clip(base + glow, 0, 255)


def _vignette(base: np.ndarray, amount: float = 0.45) -> np.ndarray:
    yy, xx = np.mgrid[0:H, 0:W]
    nx = (xx - W / 2) / (W / 2)
    ny = (yy - H / 2) / (H / 2)
    mask = np.clip(nx * nx * 0.65 + ny * ny, 0, 1)[..., None]
    return np.clip(base * (1 - amount * mask), 0, 255)


def _to_image(base: np.ndarray) -> Image.Image:
    return Image.fromarray(base.astype(np.uint8), "RGB")


def _diyas() -> Image.Image:
    rng = np.random.default_rng(2)
    base = _canvas((48, 12, 24), (92, 36, 18))
    lights = []
    for _ in range(28):
        lights.append(
            (
                float(rng.uniform(0, W)),
                float(rng.uniform(0, H * 0.72)),
                float(rng.uniform(18, 70)),
                (255, int(rng.integers(150, 210)), 70),
            )
        )
    base = _add_glow(base, lights)
    base = _vignette(base, 0.35)
    image = _to_image(base)
    draw = ImageDraw.Draw(image, "RGBA")
    for i, x in enumerate(np.linspace(70, W - 70, 11)):
        y = 150 + (18 if i % 2 else 0)
        radius = 16
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(214, 92, 28, 230))
        draw.ellipse((x - radius + 6, y - radius + 5, x + radius - 6, y + radius - 7), fill=(255, 176, 48, 240))
    for i, x in enumerate(np.linspace(120, W - 120, 7)):
        _draw_diya(draw, float(x), H - 150, 1.15 if i % 2 == 0 else 0.95)
    return image.filter(ImageFilter.SMOOTH)


def _draw_diya(draw: ImageDraw.ImageDraw, x: float, y: float, scale: float) -> None:
    w = 78 * scale
    h = 28 * scale
    draw.ellipse((x - w, y - h * 0.2, x + w, y + h), fill=(92, 28, 18, 255))
    draw.ellipse((x - w * 0.82, y - h * 0.05, x + w * 0.82, y + h * 0.72), fill=(186, 78, 32, 255))
    draw.polygon(
        [
            (x, y - 78 * scale),
            (x - 16 * scale, y - 8 * scale),
            (x + 16 * scale, y - 8 * scale),
        ],
        fill=(255, 214, 120, 230),
    )
    draw.polygon(
        [
            (x, y - 58 * scale),
            (x - 8 * scale, y - 12 * scale),
            (x + 8 * scale, y - 12 * scale),
        ],
        fill=(255, 244, 210, 240),
    )


def _rangoli() -> Image.Image:
    base = _canvas((64, 28, 22), (112, 72, 42))
    floor = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    sand = np.array([168, 112, 68], dtype=np.float32)
    base = base * (1 - floor * 0.55) + sand * (floor * 0.55)
    lights = []
    for i, x in enumerate(np.linspace(40, W - 40, 14)):
        lights.append((float(x), 210 + (30 if i % 2 else 0), 36, (255, 196, 110)))
    base = _add_glow(base, lights)
    base = _vignette(base, 0.28)
    image = _to_image(base)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    draw.arc((30, 160, W - 30, 280), 200, 340, fill=(255, 214, 140, 180), width=3)
    cx, cy = W / 2, H - 250
    colors = (
        (196, 32, 48, 210),
        (232, 164, 32, 210),
        (40, 110, 70, 200),
        (232, 92, 36, 210),
        (120, 36, 90, 190),
    )
    for ring, color in enumerate(colors):
        radius = 250 - ring * 36
        petals = 12
        for p in range(petals):
            angle = (math.tau * p / petals) + ring * 0.18
            px = cx + math.cos(angle) * radius * 0.72
            py = cy + math.sin(angle) * radius * 0.42
            rw, rh = 34 - ring * 3, 18
            _petal(draw, px, py, rw, rh, angle, color)
        draw.ellipse(
            (cx - radius * 0.28, cy - radius * 0.16, cx + radius * 0.28, cy + radius * 0.16),
            outline=color,
            width=4,
        )
    draw.ellipse((cx - 28, cy - 16, cx + 28, cy + 16), fill=(255, 214, 120, 230))
    image.paste(overlay, (0, 0), overlay)
    return image


def _petal(draw, x, y, rw, rh, angle, color) -> None:
    points = []
    for t in np.linspace(0, math.tau, 18, endpoint=False):
        px = math.cos(t) * rw
        py = math.sin(t) * rh
        rx = px * math.cos(angle) - py * math.sin(angle)
        ry = px * math.sin(angle) + py * math.cos(angle)
        points.append((x + rx, y + ry))
    draw.polygon(points, fill=color)


def _fireworks() -> Image.Image:
    rng = np.random.default_rng(7)
    base = _canvas((8, 10, 28), (18, 12, 32))
    bursts = []
    for _ in range(7):
        bx = float(rng.uniform(80, W - 80))
        by = float(rng.uniform(80, H * 0.42))
        color = (
            int(rng.integers(220, 255)),
            int(rng.integers(140, 230)),
            int(rng.integers(80, 180)),
        )
        bursts.append((bx, by, float(rng.uniform(50, 110)), color))
        for _spark in range(16):
            ang = float(rng.uniform(0, math.tau))
            dist = float(rng.uniform(20, 130))
            bursts.append(
                (
                    bx + math.cos(ang) * dist,
                    by + math.sin(ang) * dist,
                    float(rng.uniform(2, 5)),
                    color,
                )
            )
    base = _add_glow(base, bursts)
    base = _vignette(base, 0.4)
    image = _to_image(base)
    draw = ImageDraw.Draw(image, "RGBA")
    ground = H - 280
    draw.rectangle((0, ground, W, H), fill=(28, 16, 22, 255))
    draw.polygon([(0, ground), (0, ground - 220), (180, ground - 300), (180, ground)], fill=(42, 22, 32, 255))
    draw.polygon([(W, ground), (W, ground - 180), (W - 220, ground - 280), (W - 220, ground)], fill=(48, 24, 36, 255))
    draw.rectangle((260, ground - 340, 820, ground), fill=(54, 26, 38, 255))
    for x in (340, 540, 740):
        draw.rounded_rectangle((x, ground - 230, x + 90, ground - 40), radius=45, fill=(16, 10, 18, 255))
        draw.arc((x, ground - 230, x + 90, ground - 140), 180, 360, fill=(232, 176, 84, 200), width=3)
    draw.polygon([(470, ground - 430), (540, ground - 340), (600, ground - 430), (540, ground - 500)], fill=(72, 32, 44, 255))
    for x in np.linspace(80, W - 80, 9):
        _draw_diya(draw, float(x), H - 90, 0.7)
    return image


def _temple() -> Image.Image:
    base = _canvas((18, 10, 28), (48, 18, 16))
    base = _add_glow(
        base,
        [
            (W / 2, H * 0.42, 220, (255, 170, 70)),
            (W / 2, H * 0.62, 160, (255, 120, 40)),
            (180, 280, 40, (255, 200, 120)),
            (W - 180, 280, 40, (255, 200, 120)),
        ],
    )
    base = _vignette(base, 0.38)
    image = _to_image(base)
    draw = ImageDraw.Draw(image, "RGBA")
    draw.polygon(
        [
            (180, H - 200),
            (180, 460),
            (320, 300),
            (540, 180),
            (540, H - 200),
        ],
        fill=(62, 28, 24, 255),
    )
    draw.polygon(
        [
            (W - 180, H - 200),
            (W - 180, 460),
            (W - 320, 300),
            (W - 540, 180),
            (W - 540, H - 200),
        ],
        fill=(62, 28, 24, 255),
    )
    draw.rounded_rectangle((390, 430, W - 390, H - 180), radius=200, fill=(24, 10, 14, 255))
    draw.arc((390, 250, W - 390, 760), 180, 360, fill=(242, 186, 92, 230), width=8)
    for row, y in enumerate((H - 360, H - 270, H - 180)):
        count = 8 - row
        for x in np.linspace(220, W - 220, count):
            _draw_diya(draw, float(x), float(y), 0.62)
    return image
