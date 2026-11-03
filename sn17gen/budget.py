from __future__ import annotations

from dataclasses import dataclass, field

RATES = {
    "gpt-6-astra": (10, 50, 20, 75),
    "gpt-6.1-sol": (2, 10, 4, 15),
    "gpt-6-sol": (2, 10, 4, 15),
    "gpt-6-luna": (0.10, 0.50, 0.20, 0.75),
    "gpt-5.6-sol": (4, 20, 8, 30),
    "gpt-5.6-terra": (2, 12, 4, 18),
    "gpt-5.6-luna": (0.20, 1.20, 0.40, 1.80),
}
LONG_ABOVE = 272_000
CREDIT_LIMIT = 5_000_000
CALL_LIMIT = 60


def call_credits(model: str, usage: dict) -> float:
    i_s, o_s, i_l, o_l = RATES[model]
    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    if inp > LONG_ABOVE:
        return inp * i_l + out * o_l
    return inp * i_s + out * o_s


@dataclass
class Ledger:
    credit_cap: float = 4_200_000
    call_cap: int = 12
    calls: int = 0
    credits: float = 0.0
    provider_errors: int = 0
    log: list = field(default_factory=list)

    def charge(self, model: str, usage: dict | None, kind: str) -> None:
        self.calls += 1
        c = call_credits(model, usage or {})
        self.credits += c
        self.log.append((kind, model, c))

    def can_call(self, expected: float) -> bool:
        return self.calls < self.call_cap and self.credits + expected <= self.credit_cap
