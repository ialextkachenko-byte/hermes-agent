"""Startup lifecycle notifications must survive the send-path-degraded window.

Regression for a race introduced by the polling-progress health gate:
``TelegramAdapter._begin_polling_generation()`` sets
``_send_path_degraded=True`` for every new polling generation and only clears
it when ``_record_polling_progress()`` observes the first successful
getUpdates. But ``_send_home_channel_startup_notifications()`` /
``_send_restart_notification()`` fire immediately after ``[Telegram] Connected``
— often inside that window — so the very first send returns
``success=False, error='send_path_degraded', retryable=True`` and the lifecycle
message is lost silently.

The helper ``_send_with_polling_settle`` waits (bounded) for the polling
progress event and retries once before giving up.
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest


def _ensure_telegram_mock():
    if "telegram" in sys.modules and hasattr(sys.modules["telegram"], "__file__"):
        return
    mod = MagicMock()
    mod.error.NetworkError = type("NetworkError", (OSError,), {})
    mod.error.TimedOut = type("TimedOut", (OSError,), {})
    mod.error.BadRequest = type("BadRequest", (Exception,), {})
    for name in ("telegram", "telegram.ext", "telegram.constants", "telegram.request"):
        sys.modules.setdefault(name, mod)
    sys.modules.setdefault("telegram.error", mod.error)


_ensure_telegram_mock()

from gateway.run import GatewayRunner  # noqa: E402
from plugins.platforms.telegram.adapter import SendResult  # noqa: E402


def _bare_runner() -> GatewayRunner:
    # Skip __init__ (needs config / plugins / IO); we only exercise one method.
    return object.__new__(GatewayRunner)


class _FakeAdapter:
    """Mimic TelegramAdapter's send-path-degraded gate around ``send()``."""

    def __init__(self):
        self._send_path_degraded = True
        self._polling_progress_event = asyncio.Event()
        self.calls: list[tuple[str, str]] = []

    async def send(self, chat_id, message, metadata=None):
        self.calls.append((chat_id, message))
        if self._send_path_degraded:
            return SendResult(success=False, error="send_path_degraded", retryable=True)
        return SendResult(success=True, message_id=len(self.calls))


@pytest.mark.asyncio
async def test_startup_send_retries_after_polling_progress_clears():
    """The first send lands during degraded window; second succeeds after progress."""
    runner = _bare_runner()
    adapter = _FakeAdapter()

    async def clear_after(delay: float):
        await asyncio.sleep(delay)
        adapter._send_path_degraded = False
        adapter._polling_progress_event.set()

    clearer = asyncio.create_task(clear_after(0.01))
    result = await runner._send_with_polling_settle(
        adapter, "123", "♻️ Gateway online", settle_timeout=5.0
    )
    await clearer

    assert result.success is True
    assert len(adapter.calls) == 2  # first attempt (degraded) + retry


@pytest.mark.asyncio
async def test_startup_send_gives_up_when_progress_never_arrives():
    """If getUpdates never progresses within timeout, return the original failure."""
    runner = _bare_runner()
    adapter = _FakeAdapter()

    result = await runner._send_with_polling_settle(
        adapter, "123", "♻️ Gateway online", settle_timeout=0.05
    )

    assert result.success is False
    assert result.error == "send_path_degraded"
    assert len(adapter.calls) == 1  # only the initial attempt; no retry


@pytest.mark.asyncio
async def test_startup_send_passes_through_healthy_result():
    """Healthy adapter: helper does not double-send."""
    runner = _bare_runner()
    adapter = _FakeAdapter()
    adapter._send_path_degraded = False
    adapter._polling_progress_event.set()

    result = await runner._send_with_polling_settle(
        adapter, "123", "hello", settle_timeout=5.0
    )

    assert result.success is True
    assert len(adapter.calls) == 1


@pytest.mark.asyncio
async def test_startup_send_does_not_retry_non_retryable_failure():
    """Non-retryable failures (e.g. Chat not found) must not be retried."""
    runner = _bare_runner()

    class _PermFail:
        _send_path_degraded = False
        _polling_progress_event = asyncio.Event()

        def __init__(self):
            self.calls = 0

        async def send(self, chat_id, message, metadata=None):
            self.calls += 1
            return SendResult(success=False, error="Chat not found", retryable=False)

    adapter = _PermFail()
    result = await runner._send_with_polling_settle(
        adapter, "123", "hello", settle_timeout=5.0
    )

    assert result.success is False
    assert adapter.calls == 1


@pytest.mark.asyncio
async def test_startup_send_works_with_non_telegram_adapter():
    """Adapters without polling-progress machinery get result passed through."""
    runner = _bare_runner()

    class _MinimalAdapter:
        def __init__(self):
            self.calls = 0

        async def send(self, chat_id, message, metadata=None):
            self.calls += 1
            return SendResult(success=False, error="whatever", retryable=True)

    adapter = _MinimalAdapter()
    result = await runner._send_with_polling_settle(
        adapter, "123", "hello", settle_timeout=5.0
    )

    assert result.success is False
    assert adapter.calls == 1  # no retry — no progress event to wait on
