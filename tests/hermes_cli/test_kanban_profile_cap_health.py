"""Health telemetry helpers for per-profile concurrency caps (#D2-2)."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest


@pytest.fixture()
def isolated_kanban_home_with_profiles(monkeypatch):
    test_home = tempfile.mkdtemp(prefix="kanban_profile_cap_health_test_")
    for prof in ("alpha", "default"):
        os.makedirs(os.path.join(test_home, "profiles", prof), exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", test_home)
    for mod in list(sys.modules.keys()):
        if mod.startswith("hermes_cli") or mod.startswith("hermes_state") or mod == "hermes_constants":
            del sys.modules[mod]
    from hermes_cli import kanban_db
    yield kanban_db


def test_profile_cap_health_warning_message():
    from hermes_cli import kanban_db as kb

    msg = kb.profile_cap_health_warning(
        [("t1", "coder", 1), ("t2", "coder", 1)],
        max_in_progress_per_profile=1,
    )
    assert "per-profile cap hit" in msg
    assert "max_in_progress_per_profile=1" in msg
    assert "2 task(s) waiting" in msg
    assert "coder has 1 worker(s) in flight" in msg
    assert "stuck" not in msg
    assert "venv" not in msg


def _fake_spawn(*_args, **_kwargs):
    return 12345


def test_profile_cap_idle_explains_zero_spawns_when_only_capped(
    isolated_kanban_home_with_profiles,
):
    kb = isolated_kanban_home_with_profiles
    with kb.connect_closing() as conn:
        kb.create_board(slug="default", name="Test")
        for i in range(2):
            kb.create_task(conn, title=f"a{i}", assignee="alpha")

    with kb.connect_closing() as conn:
        kb.dispatch_once(
            conn,
            spawn_fn=_fake_spawn,
            dry_run=False,
            max_in_progress_per_profile=1,
        )

    with kb.connect_closing() as conn:
        kb.create_task(conn, title="a-extra", assignee="alpha")
        res = kb.dispatch_once(
            conn,
            dry_run=True,
            max_in_progress_per_profile=1,
        )

    assert res.skipped_per_profile_capped
    assert not res.spawned
    assert kb.profile_cap_idle_explains_zero_spawns(
        [("default", res)],
        max_in_progress_per_profile=1,
    )
