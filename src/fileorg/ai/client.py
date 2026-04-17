from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

try:
    import ollama as _ollama
except ImportError:
    _ollama = None  # type: ignore[assignment]

from fileorg.ai.prompts import SYSTEM_PROMPT

_FALLBACK: dict = {"category": "Uncategorized", "confidence": 0.0, "reasoning": ""}


class OllamaClient:
    def __init__(self, model: str = "llama3.2", timeout: int = 120) -> None:
        self.model = model
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            if _ollama is None:
                return False
            models = _ollama.list()
            return any(
                m["model"].startswith(self.model)
                for m in models.get("models", [])
            )
        except Exception:
            return False

    def categorize(self, user_prompt: str) -> dict:
        def _call() -> dict:
            if _ollama is None:
                raise RuntimeError("ollama not installed")
            response = _ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                format="json",
                options={"num_predict": 200},
            )
            raw = response["message"]["content"]
            parsed = json.loads(raw)
            return {
                "category": str(parsed.get("category", "Uncategorized")),
                "confidence": max(0.0, min(1.0, float(parsed.get("confidence", 0.0)))),
                "reasoning": str(parsed.get("reasoning", "")),
            }

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_call)
                return future.result(timeout=self.timeout)
        except FuturesTimeoutError:
            return dict(_FALLBACK)
        except Exception:
            return dict(_FALLBACK)
