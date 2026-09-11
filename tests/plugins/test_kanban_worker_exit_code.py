"""Kanban worker quiet-mode exit codes (cli._resolve_quiet_mode_exit_code)."""

from __future__ import annotations

import pytest

from cli import _resolve_quiet_mode_exit_code
from hermes_cli import kanban_db as kb


@pytest.mark.parametrize(
    "failure_reason",
    [
        "rate_limit",
        "billing",
        "timeout",
        "server_error",
        "overloaded",
        "auth",
    ],
)
def test_kanban_transient_provider_failure_exits_rate_limit_code(failure_reason):
    result = {"failed": True, "failure_reason": failure_reason}
    assert (
        _resolve_quiet_mode_exit_code(result, kanban_worker=True)
        == kb.KANBAN_RATE_LIMIT_EXIT_CODE
    )


def test_kanban_logical_failure_exits_generic_error():
    result = {"failed": True, "failure_reason": "content_policy_blocked"}
    assert _resolve_quiet_mode_exit_code(result, kanban_worker=True) == 1


def test_non_kanban_failed_run_stays_generic_error_even_for_transport():
    result = {"failed": True, "failure_reason": "timeout"}
    assert _resolve_quiet_mode_exit_code(result, kanban_worker=False) == 1


def test_non_kanban_success_stays_zero():
    assert _resolve_quiet_mode_exit_code({"failed": False}, kanban_worker=False) == 0
