from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from renderer_client import RenderOptions, RenderRejected

from sn17gen.pipeline import run as pipeline_run

__all__ = ["generate"]


async def generate(image: bytes, seed: int, witness) -> str | None:
    bridge = _Bridge(witness, asyncio.get_running_loop())
    return await asyncio.to_thread(pipeline_run, image, seed, bridge, bridge)


class _Bridge:

    def __init__(self, witness, loop: asyncio.AbstractEventLoop) -> None:
        self.witness, self.loop = witness, loop
        try:
            from witness_client import RenderOptions as options_type
        except ImportError:
            options_type = RenderOptions
        self.options_type = options_type

    def wait(self, awaitable):
        return asyncio.run_coroutine_threadsafe(_awaited(awaitable), self.loop).result()

    @property
    def responses(self) -> "_Bridge":
        return self

    def create(self, *, request_id: int = 0, **kw):
        return self.wait(self.witness.responses.create(request_id=request_id, **kw))

    def render(self, source: str, options: RenderOptions = RenderOptions()) -> bytes:
        if self.options_type is not RenderOptions:
            options = self.options_type(**{k: getattr(options, k) for k in RenderOptions.__dataclass_fields__})
        try:
            return self.wait(self.witness.render(source, options))
        except RenderRejected:
            raise
        except Exception as e:
            if type(e).__name__ != "RenderRejected":
                raise
            detail = getattr(e, "detail_json", None) or json.dumps({"error": str(e) or "rejected"})
            raise RenderRejected(detail) from e


async def _awaited(awaitable):
    return await awaitable


async def main() -> None:
    from miner.run import run

    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--prompts", type=Path, help="Text file with one image URL per line")
    inputs.add_argument("--image", action="append", help="Image file or HTTP(S) URL; repeat for a small batch")
    parser.add_argument("--seed", type=int, required=True, help="Published round seed")
    parser.add_argument("--parallel-prompts", type=int, default=8, help="Active prompts (default: 8)")
    parser.add_argument("--parallel-calls", type=int, default=12)
    parser.add_argument("--attempts", type=int, default=3, help="Maximum passes over unfinished prompts (default: 3)")
    parser.add_argument("--wallet-name", default="miner")
    parser.add_argument("--wallet-hotkey", default="default")
    parser.add_argument("--wallet-path", default="~/.bittensor/wallets")
    parser.add_argument("--api", action="store_true", help="Use OPENAI_API_KEY instead of a local Codex subscription")
    args = parser.parse_args()

    if args.prompts:
        sources = [line.strip() for line in args.prompts.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        sources = args.image

    await run(
        generate,
        {Path(source).stem: source for source in sources},
        args.seed,
        workers=args.parallel_prompts,
        parallel_calls=args.parallel_calls,
        attempts=args.attempts,
        wallet_name=args.wallet_name,
        wallet_hotkey=args.wallet_hotkey,
        wallet_path=args.wallet_path,
        api=args.api,
    )


if __name__ == "__main__":
    asyncio.run(main())
