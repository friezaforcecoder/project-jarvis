from __future__ import annotations

from jarvis_core import __main__ as jarvis_main


class HealthyResponse:
    status = 200

    def __enter__(self) -> HealthyResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_hud_url_uses_loopback_for_wildcard_bind_addresses() -> None:
    assert jarvis_main._hud_url("0.0.0.0", 8000) == "http://127.0.0.1:8000"
    assert jarvis_main._hud_url("::", 9000) == "http://127.0.0.1:9000"
    assert jarvis_main._hud_url("localhost", 7000) == "http://localhost:7000"


def test_open_hud_waits_for_healthy_core(monkeypatch) -> None:
    opened: list[str] = []
    requested: list[tuple[str, float]] = []

    def fake_urlopen(url: str, timeout: float) -> HealthyResponse:
        requested.append((url, timeout))
        return HealthyResponse()

    monkeypatch.setattr(jarvis_main.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(jarvis_main.webbrowser, "open", lambda url: opened.append(url) or True)

    result = jarvis_main._open_hud_when_ready("http://127.0.0.1:8123")

    assert result is True
    assert requested == [("http://127.0.0.1:8123/v1/health", 1.0)]
    assert opened == ["http://127.0.0.1:8123"]


def test_main_starts_hud_opener_only_when_requested(monkeypatch) -> None:
    started_threads: list[dict[str, object]] = []
    uvicorn_calls: list[dict[str, object]] = []

    class FakeThread:
        def __init__(self, **kwargs: object) -> None:
            started_threads.append(kwargs)

        def start(self) -> None:
            started_threads[-1]["started"] = True

    monkeypatch.setattr(jarvis_main.threading, "Thread", FakeThread)
    monkeypatch.setattr(
        jarvis_main.uvicorn,
        "run",
        lambda app, **kwargs: uvicorn_calls.append({"app": app, **kwargs}),
    )

    jarvis_main.main(["--open"])

    assert len(started_threads) == 1
    assert started_threads[0]["name"] == "jarvis-hud-opener"
    assert started_threads[0]["daemon"] is True
    assert started_threads[0]["started"] is True
    assert uvicorn_calls == [
        {
            "app": "jarvis_core.api:app",
            "host": "127.0.0.1",
            "port": 8000,
            "log_config": None,
        }
    ]


def test_main_without_open_starts_only_core(monkeypatch) -> None:
    threads: list[object] = []
    uvicorn_calls: list[object] = []

    monkeypatch.setattr(
        jarvis_main.threading,
        "Thread",
        lambda **kwargs: threads.append(kwargs),
    )
    monkeypatch.setattr(
        jarvis_main.uvicorn,
        "run",
        lambda *args, **kwargs: uvicorn_calls.append((args, kwargs)),
    )

    jarvis_main.main([])

    assert threads == []
    assert len(uvicorn_calls) == 1
