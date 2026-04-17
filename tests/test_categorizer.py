from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from fileorg.ai.client import OllamaClient
from fileorg.ai.prompts import build_user_prompt


def _mock_clues(*pairs: tuple[str, str, str, float]):
    rows = []
    for plugin, key, val, conf in pairs:
        r = MagicMock()
        r.__getitem__ = lambda self, k, _p=plugin, _k=key, _v=val, _c=conf: {
            "plugin_name": _p, "key": _k, "value": _v, "confidence": _c
        }[k]
        rows.append(r)
    return rows


def test_categorize_success() -> None:
    client = OllamaClient()
    with patch("fileorg.ai.client._ollama") as mock_ollama:
        mock_ollama.chat.return_value = {
            "message": {"content": '{"category":"Documents/Reports","confidence":0.9,"reasoning":"Looks like a report"}'}
        }
        result = client.categorize("test prompt")
    assert result["category"] == "Documents/Reports"
    assert result["confidence"] == 0.9


def test_categorize_parse_failure_returns_fallback() -> None:
    client = OllamaClient()
    with patch("fileorg.ai.client._ollama") as mock_ollama:
        mock_ollama.chat.return_value = {"message": {"content": "not json at all"}}
        result = client.categorize("test")
    assert result["category"] == "Uncategorized"
    assert result["confidence"] == 0.0


def test_categorize_exception_returns_fallback() -> None:
    client = OllamaClient()
    with patch("fileorg.ai.client._ollama") as mock_ollama:
        mock_ollama.chat.side_effect = ConnectionError("Ollama not running")
        result = client.categorize("test")
    assert result["category"] == "Uncategorized"


def test_build_user_prompt_contains_filename(tmp_path: Path) -> None:
    f = tmp_path / "my_document.pdf"
    f.write_bytes(b"%PDF")
    clues = _mock_clues(("filename", "extension", "pdf", 1.0))
    prompt = build_user_prompt(f, "application/pdf", clues)
    assert "my_document.pdf" in prompt
    assert "pdf" in prompt
    assert "Categorize this file" in prompt


def test_is_available_checks_model() -> None:
    client = OllamaClient(model="llama3.2")
    with patch("fileorg.ai.client._ollama") as mock_ollama:
        mock_ollama.list.return_value = {"models": [{"model": "llama3.2:latest"}]}
        assert client.is_available() is True
        mock_ollama.list.return_value = {"models": [{"model": "mistral:latest"}]}
        assert client.is_available() is False
