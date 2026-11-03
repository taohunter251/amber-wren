"""The last step: the judge's wording on the four front views, both orders, between the two families' modules. Tie: the second."""
from __future__ import annotations

import asyncio
import json
import re

from witness_client import RenderOptions

from . import prompts, views
from .pipeline import _png, _provider_failure

MODEL, EFFORT, MAX_OUTPUT, FIRST_ID = "gpt-6.1-sol", "low", 1024, 5000


async def _shots(source: str, witness) -> list[bytes]:
    return [await witness.render(source, RenderOptions(thetas=(float(t),), phis=(float(p),), img_size=1024, bg_color="ffffff", lighting="neutral", cam_radius=2.0, cam_fov_deg=49.1)) for t, p, _ in prompts.JUDGE_VIEWS]


async def choose(image: bytes, first: str | None, second: str | None, witness) -> str | None:
    if first is None or second is None:
        return second if first is None else first
    try:
        a, b = await _shots(first, witness), await _shots(second, witness)
    except Exception as exc:
        if type(exc).__name__ != "RenderRejected":
            raise
        return second
    ref = views.data_url(_png(image))
    pen = [0.0, 0.0]

    async def ask(k: int, v: int, swap: bool) -> None:
        one, two = (b, a) if swap else (a, b)
        content = [{"type": "input_text", "text": "Reference image (target object):"}, {"type": "input_image", "image_url": ref, "detail": "high"},
                   {"type": "input_text", "text": "3D model 1:"}, {"type": "input_image", "image_url": views.data_url(one[v]), "detail": "high"},
                   {"type": "input_text", "text": "3D model 2:"}, {"type": "input_image", "image_url": views.data_url(two[v]), "detail": "high"},
                   {"type": "input_text", "text": prompts.JUDGE_USER.format(angle_desc=prompts.JUDGE_VIEWS[v][2])}]
        try:
            result = await witness.responses.create(request_id=FIRST_ID + k, model=MODEL, instructions=prompts.JUDGE_SYSTEM, reasoning={"effort": EFFORT},
                                                    service_tier="default", max_output_tokens=MAX_OUTPUT, input=[{"role": "user", "content": content}])
        except Exception as exc:
            if getattr(exc, "source", None) != "provider" and not _provider_failure(exc):
                raise
            return
        m = re.search(r"\{.*\}", getattr(result, "output_text", None) or "", re.S)
        try:
            d = json.loads(m.group(0)) if m else {}
            p1, p2 = float(d["penalty_1"]), float(d["penalty_2"])
        except (ValueError, KeyError, TypeError):
            return
        pen[1 if swap else 0] += p1
        pen[0 if swap else 1] += p2

    await asyncio.gather(*[ask(2 * v + s, v, bool(s)) for v in range(len(prompts.JUDGE_VIEWS)) for s in (0, 1)])
    return first if pen[0] < pen[1] else second
