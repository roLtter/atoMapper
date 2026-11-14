from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _block_real_llm(monkeypatch: pytest.MonkeyPatch):
    """CI/local tests must not hit a real LLM endpoint by accident."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("LLM_MODEL", "ci-blocked")

    def _boom(*_a, **_k):
        raise RuntimeError("real LLM provider blocked in tests; pass llm=FakeLLM/oracle_llm")

    monkeypatch.setattr("mapper.pipeline.make_llm_provider", _boom)
