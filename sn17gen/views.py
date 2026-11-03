from __future__ import annotations

import base64
import io

from PIL import Image

SHEET = ((30, 0), (330, 0), (0, 15), (0, -30))
VIEW_PX = 512


def view_options(theta: int, phi: int, px: int = VIEW_PX):
    fields = {"thetas": [theta], "phis": [phi], "img_size": px, "bg_color": "ffffff",
              "lighting": "neutral", "cam_radius": 2.0, "cam_fov_deg": 49.1}
    try:
        from renderer_client import RenderOptions
    except ImportError:
        return fields
    try:
        return RenderOptions(thetas=(float(theta),), phis=(float(phi),), img_size=px, bg_color="ffffff",
                             lighting="neutral", cam_radius=2.0, cam_fov_deg=49.1)
    except TypeError:
        return fields


def grid_options(pairs, px: int):
    thetas, phis = [t for t, _ in pairs], [p for _, p in pairs]
    fields = {"thetas": thetas, "phis": phis, "img_size": px, "bg_color": "ffffff",
              "lighting": "neutral", "cam_radius": 2.0, "cam_fov_deg": 49.1, "gap": 0}
    try:
        from renderer_client import RenderOptions
    except ImportError:
        return fields
    try:
        return RenderOptions(thetas=tuple(float(t) for t in thetas), phis=tuple(float(p) for p in phis),
                             img_size=px, bg_color="ffffff", lighting="neutral", cam_radius=2.0,
                             cam_fov_deg=49.1, gap=0)
    except TypeError:
        return fields


def _sheet(render, source: str, pairs, px: int) -> bytes:
    im = Image.open(io.BytesIO(render(source, grid_options(pairs, px)))).convert("RGB")
    if im.size != (2 * px, 2 * px):
        gap = im.size[0] - 2 * px
        if im.size[0] == im.size[1] and gap > 0:
            canvas = Image.new("RGB", (2 * px, 2 * px), (255, 255, 255))
            for i in range(len(pairs)):
                x, y = (i % 2) * (px + gap), (i // 2) * (px + gap)
                canvas.paste(im.crop((x, y, x + px, y + px)), ((i % 2) * px, (i // 2) * px))
            im = canvas
        else:
            im = im.resize((2 * px, 2 * px), Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    im.save(buf, format="PNG", compress_level=6)
    return buf.getvalue()


def sheet(render, source: str) -> bytes:
    return _sheet(render, source, SHEET, VIEW_PX)


FRONT = ((30, 0), (330, 0), (0, 15), (0, -30))
FRONT_PX = 384


def front_sheet(render, source: str) -> bytes:
    return _sheet(render, source, FRONT, FRONT_PX)


def data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
