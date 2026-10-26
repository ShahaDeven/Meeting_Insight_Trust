"""Anthropic client plus a hard spend cap, shared by the extractor and the judge.

Every response's usage is priced and appended to data/results/llm_usage.jsonl, so the
README's cost-per-meeting figure comes from real calls, not estimates.
"""

import json
import os
import threading
import time

import anthropic

from core.config import MAX_USD, PRICES, RESULTS

USAGE_LOG = RESULTS / "llm_usage.jsonl"
# Without a key (e.g. CI) the client is still constructible, so modules import cleanly;
# any real call then fails loudly with an authentication error.
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY") or "not-set", max_retries=5)


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    def __init__(self, max_usd: float = MAX_USD):
        self.max_usd = max_usd
        self.spent = 0.0
        self._lock = threading.Lock()

    def check(self) -> None:
        if self.spent >= self.max_usd:
            raise BudgetExceeded(f"spent ${self.spent:.2f} of ${self.max_usd:.2f} cap")

    def charge(self, model: str, usage, tag: str, seconds: float) -> float:
        tokens_in = (usage.input_tokens + (usage.cache_creation_input_tokens or 0)
                     + (usage.cache_read_input_tokens or 0))
        rate_in, rate_out = PRICES[model]
        if model == "claude-haiku-5-5" and tokens_in > 100_000:
            rate_in, rate_out = 0.50, 2.50
        cost = (tokens_in * rate_in + usage.output_tokens * rate_out) / 1e6
        row = {"tag": tag, "model": model, "input_tokens": tokens_in,
               "output_tokens": usage.output_tokens, "usd": round(cost, 6),
               "seconds": round(seconds, 1), "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        with self._lock:
            self.spent += cost
            USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
            with USAGE_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
        return cost
