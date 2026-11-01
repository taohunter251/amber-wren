from __future__ import annotations

import hashlib
import io
import json
import os
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

from . import prompts, views
from .budget import Ledger
from .jsutil import extract, final, wrap

MODEL = "gpt-6.1-sol"
EFFORT = "medium"
REFINE_EFFORT = "high"
SERVICE_TIER = "default"
CALLS = 3
REPAIRS = 1
CHAINS = 3
STARTS = (prompts.GEN_USER, prompts.GEN_USER_ALT, prompts.GEN_USER)
PANEL_MODEL = "gpt-6-astra"
PANEL_EFFORT = "low"
PROVIDER_RETRIES = 2
BACKOFF_SECONDS = 5
EXPECTED_CALL_CREDITS = 450_000
EXPECTED_PANEL_CREDITS = 150_000
CHAIN_CREDITS = 1_350_000
CHAIN_CALLS = CALLS + REPAIRS + PROVIDER_RETRIES
ID_BLOCK = 100
FINAL_IDS = 900
FINAL_REFINE_ID = 950
EXTRA_REFINE_ID = 960
PICK_EFFORT = "low"
PICK_PX = 1024
PICK_CALL_CREDITS = 40_000
FINAL_REFINE_CREDITS = 600_000
TOTAL_CREDITS = 4_600_000
_CHARGE_LOCK = threading.Lock()
_TRACE_LOCK = threading.Lock()


def _trace(key: str, stage: str, source: str | None) -> None:
    folder = os.environ.get("SN17_TRACE_DIR")
    if not folder or source is None:
        return
    path = os.path.join(folder, key)
    with _TRACE_LOCK:
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "stages.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"stage": stage, "source": source}) + "\n")


def _png(image: bytes) -> bytes:
    im = Image.open(io.BytesIO(image)).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, format="PNG", compress_level=6)
    return buf.getvalue()


def _call(witness, ledger: Ledger, rid: int, kind: str, text: str, pngs: list[bytes], *, model: str | None = None,
          effort: str | None = None, instructions: str | None = None, content: list | None = None) -> str | None:
    model, effort = model or MODEL, effort or EFFORT
    instructions = prompts.GEN_SYSTEM if instructions is None else instructions
    if content is None:
        content = [{"type": "input_text", "text": text}]
        content += [{"type": "input_image", "image_url": views.data_url(p), "detail": "high"} for p in pngs]
    try:
        result = witness.responses.create(
            request_id=rid, model=model, instructions=instructions,
            reasoning={"effort": effort}, service_tier=SERVICE_TIER,
            input=[{"role": "user", "content": content}],
        )
    except Exception as exc:
        if getattr(exc, "source", None) != "provider" and not _provider_failure(exc):
            raise
        if getattr(exc, "status_code", None) == 429 or type(exc).__name__ in ("APIConnectionError", "APITimeoutError"):
            raise
        with _CHARGE_LOCK:
            ledger.charge(model, None, kind)
            ledger.provider_errors += 1
        time.sleep(BACKOFF_SECONDS)
        return None
    usage = getattr(result, "usage", None) or {}
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    with _CHARGE_LOCK:
        ledger.charge(model, usage, kind)
    return getattr(result, "output_text", None)


def _provider_failure(exc) -> bool:
    try:
        import openai
    except ImportError:
        return False
    return isinstance(exc, openai.APIError)


def _rejection(exc) -> str:
    return str(getattr(exc, "detail_json", None) or getattr(exc, "detail", None) or exc)[:1500]


def _sheet_or_error(renderer, source: str) -> tuple[bytes | None, str | None]:
    try:
        return views.sheet(renderer.render, source), None
    except Exception as exc:
        if type(exc).__name__ != "RenderRejected":
            raise
        return None, _rejection(exc)


def _parallel(jobs: list[Callable[[], str | None]]) -> list[str | None]:
    if not jobs:
        return []
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [pool.submit(job) for job in jobs]
        return [f.result() for f in futures]


class _Chain:

    def __init__(self, idx: int, key: str) -> None:
        self.idx, self.key, self.base = idx, key, (idx + 1) * ID_BLOCK
        self.ledger = Ledger(credit_cap=CHAIN_CREDITS, call_cap=CHAIN_CALLS)
        self.stop, self.spare, self.retries, self.seen = CALLS, REPAIRS, PROVIDER_RETRIES, 0
        self.best: str | None = None
        self.best_sheet: bytes | None = None
        self.js: str | None = None
        self.err: str | None = None
        self.step = 0
        self.done = False

    def settle(self, renderer, kind: str) -> None:
        self.err = None
        if self.js is None:
            return
        wrapped = wrap(self.js)
        if wrapped is None:
            self.err = "the module must contain `export default function generate(THREE)`"
            return
        sheet, self.err = _sheet_or_error(renderer, wrapped)
        if self.err is None:
            self.best, self.best_sheet = self.js, sheet
            _trace(self.key, f"c{self.idx}.{self.step}.{kind}", wrapped)

    def next_job(self, witness, ref: bytes) -> tuple[Callable, str] | None:
        while self.ledger.provider_errors > self.seen:
            self.seen += 1
            if self.retries > 0:
                self.retries -= 1
                self.stop += 1
        if self.ledger.calls >= self.stop and self.best is None and self.spare > 0:
            self.spare -= 1
            self.stop += 1
        if self.ledger.calls >= self.stop or not self.ledger.can_call(EXPECTED_CALL_CREDITS):
            self.done = True
            return None
        if self.js is None and self.best is None:
            kind, pngs = "gen", [ref]
            text = STARTS[self.idx % len(STARTS)] if self.ledger.calls == 0 else prompts.GEN_USER
            effort = EFFORT if self.ledger.calls == 0 else REFINE_EFFORT
        elif self.err is not None:
            kind, text, pngs, effort = "repair", prompts.REPAIR_USER % (self.err, self.js), [ref], REFINE_EFFORT
        else:
            kind, text, pngs, effort = "refine", prompts.REFINE_USER % self.best, [ref, self.best_sheet], REFINE_EFFORT
        rid = self.base + self.ledger.calls

        def job():
            return extract(_call(witness, self.ledger, rid, kind, text, pngs, effort=effort))
        return job, kind


def _penalties(text: str | None, n: int) -> list[float] | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        pens = [float(x) for x in json.loads(m.group(0))["penalties"]] if m else []
    except (ValueError, KeyError, TypeError):
        pens = []
    return pens if len(pens) == n else None


def _panel(witness, renderer, ref: bytes, modules: list[str]) -> str:
    sheets = [views.front_sheet(renderer.render, wrap(js)) for js in modules]
    n = len(modules)
    ledger = Ledger(credit_cap=2 * EXPECTED_PANEL_CREDITS + 1, call_cap=2)
    orders = (list(range(n)), list(range(n))[::-1])

    def job(k: int):
        def ask():
            order = orders[k]
            text = _call(witness, ledger, FINAL_IDS + k, "pick", prompts.PANEL_USER % (n + 1),
                         [ref, *[sheets[i] for i in order]], model=PANEL_MODEL, effort=PANEL_EFFORT,
                         instructions=prompts.PICK_SYSTEM)
            pens = _penalties(text, n)
            if pens is None:
                return None
            out = [0.0] * n
            for pos, i in enumerate(order):
                out[i] = pens[pos]
            return out
        return ask

    votes = [v for v in _parallel([job(0), job(1)]) if v is not None]
    if not votes:
        return modules[0]
    total = [sum(col) for col in zip(*votes)]
    return modules[min(range(n), key=lambda i: (total[i], i))]


def _pair_penalties(text: str | None) -> tuple[float, float]:
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
        return float(d["penalty_1"]), float(d["penalty_2"])
    except (ValueError, KeyError, TypeError):
        return 5.0, 5.0


def _judge_pick(witness, renderer, ref: bytes, modules: list[str]) -> str:
    shots: dict[int, list[bytes]] = {}
    for i, js in enumerate(modules):
        try:
            shots[i] = [renderer.render(final(js), views.view_options(t, p, PICK_PX)) for t, p, _ in prompts.JUDGE_VIEWS]
        except Exception as exc:
            if type(exc).__name__ != "RenderRejected":
                raise
    alive = sorted(shots)
    if len(alive) < 2:
        return modules[alive[0]] if alive else modules[0]
    asks = [(x, y, v) for a in alive for b in alive if a < b for x, y in ((a, b), (b, a)) for v in range(len(prompts.JUDGE_VIEWS))]
    ledger = Ledger(credit_cap=len(asks) * PICK_CALL_CREDITS + 1, call_cap=len(asks))

    def job(k: int, x: int, y: int, v: int):
        content = [{"type": "input_text", "text": "Reference image (target object):"},
                   {"type": "input_image", "image_url": views.data_url(ref), "detail": "high"},
                   {"type": "input_text", "text": "3D model 1:"},
                   {"type": "input_image", "image_url": views.data_url(shots[x][v]), "detail": "high"},
                   {"type": "input_text", "text": "3D model 2:"},
                   {"type": "input_image", "image_url": views.data_url(shots[y][v]), "detail": "high"},
                   {"type": "input_text", "text": prompts.JUDGE_USER.format(angle_desc=prompts.JUDGE_VIEWS[v][2])}]
        return lambda: _call(witness, ledger, FINAL_IDS + k, "pick", "", [], effort=PICK_EFFORT,
                             instructions=prompts.JUDGE_SYSTEM, content=content)

    answers = _parallel([job(k, x, y, v) for k, (x, y, v) in enumerate(asks)])
    pen = {i: 0.0 for i in alive}
    for (x, y, _), text in zip(asks, answers):
        p1, p2 = _pair_penalties(text)
        pen[x] += p1
        pen[y] += p2
    return modules[min(alive, key=lambda i: (pen[i], i))]


def _final_refine(witness, renderer, ref: bytes, best: str, sheet: bytes, text: str | None = None,
                  rid: int = FINAL_REFINE_ID) -> str:
    ledger = Ledger(credit_cap=FINAL_REFINE_CREDITS + 1, call_cap=1)
    text = prompts.FINAL_REFINE_USER if text is None else text
    js = extract(_call(witness, ledger, rid, "final", text % best, [ref, sheet], effort=REFINE_EFFORT))
    wrapped = wrap(js) if js is not None else None
    if wrapped is None:
        return best
    _, err = _sheet_or_error(renderer, wrapped)
    return best if err is not None else js


def run(image: bytes, seed: int, witness, renderer) -> str | None:
    ref = _png(image)
    key = hashlib.sha256(image).hexdigest()[:16]
    chains = [_Chain(i, key) for i in range(CHAINS)]
    while True:
        planned = [(c, c.next_job(witness, ref)) for c in chains if not c.done]
        planned = [(c, p) for c, p in planned if p is not None]
        if not planned:
            break
        results = _parallel([job for _, (job, _) in planned])
        for (c, (_, kind)), js in zip(planned, results):
            c.js = js
            c.step += 1
            c.settle(renderer, kind)
    found = [c.best for c in chains if c.best is not None]
    spent = sum(c.ledger.credits for c in chains)
    pick_cost = len(found) * (len(found) - 1) * len(prompts.JUDGE_VIEWS) * PICK_CALL_CREDITS
    if len(found) > 1 and spent + pick_cost + FINAL_REFINE_CREDITS <= TOTAL_CREDITS:
        best = _judge_pick(witness, renderer, ref, found)
    elif len(found) > 1 and spent + 2 * EXPECTED_PANEL_CREDITS <= TOTAL_CREDITS:
        best = _panel(witness, renderer, ref, found)
    else:
        best = found[0] if found else None
    used = spent + (pick_cost if len(found) > 1 and spent + pick_cost + FINAL_REFINE_CREDITS <= TOTAL_CREDITS
                    else 2 * EXPECTED_PANEL_CREDITS)
    if best is not None and spent + 2 * EXPECTED_PANEL_CREDITS + FINAL_REFINE_CREDITS <= TOTAL_CREDITS:
        sheet = next(c.best_sheet for c in chains if c.best is best)
        best = _final_refine(witness, renderer, ref, best, sheet)
        used += FINAL_REFINE_CREDITS
        for k, text in enumerate(prompts.EXTRA_REFINES):
            if used + FINAL_REFINE_CREDITS > TOTAL_CREDITS:
                break
            sheet, err = _sheet_or_error(renderer, wrap(best))
            if err is not None:
                break
            best = _final_refine(witness, renderer, ref, best, sheet, text, EXTRA_REFINE_ID + 10 * k)
            used += FINAL_REFINE_CREDITS
    out = final(best) if best is not None else None
    _trace(key, "final", out)
    if out is None:
        raise RuntimeError("no valid module")
    return out
