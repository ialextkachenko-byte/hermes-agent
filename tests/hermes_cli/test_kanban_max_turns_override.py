"""Per-task max_turns_override → HERMES_MAX_ITERATIONS at worker spawn."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hermes_cli import kanban_db as kb


@pytest.fixture
def kanban_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kb.init_db()
    return home


def _minimal_task(**overrides):
    base = {
        "id": "t_turns",
        "title": "iter budget",
        "body": None,
        "assignee": "default",
        "status": "running",
        "priority": 0,
        "created_by": "test",
        "created_at": 1,
        "started_at": None,
        "completed_at": None,
        "workspace_kind": "scratch",
        "workspace_path": None,
        "claim_lock": None,
        "claim_expires": None,
        "tenant": None,
    }
    base.update(overrides)
    return kb.Task(**base)


def test_create_task_persists_max_turns_override(kanban_home):
    with kb.connect() as conn:
        tid = kb.create_task(
            conn,
            title="big card",
            assignee="worker",
            max_turns_override=200,
        )
        task = kb.get_task(conn, tid)
    assert task is not None
    assert task.max_turns_override == 200


def test_default_spawn_sets_max_iterations_env(kanban_home, monkeypatch, tmp_path):
    captured = {}

    class FakeProc:
        pid = 9999

    def fake_popen(cmd, *args, **kwargs):
        captured["env"] = dict(kwargs.get("env") or {})
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(kb, "_resolve_hermes_argv", lambda: ["hermes"])
    monkeypatch.delenv("HERMES_MAX_ITERATIONS", raising=False)

    workspace = tmp_path / "ws"
    workspace.mkdir()
    task = _minimal_task(max_turns_override=180)
    kb._default_spawn(task, str(workspace))

    assert captured["env"]["HERMES_MAX_ITERATIONS"] == "180"


def test_default_spawn_omits_max_iterations_without_override(
    kanban_home, monkeypatch, tmp_path,
):
    captured = {}

    class FakeProc:
        pid = 9998

    def fake_popen(cmd, *args, **kwargs):
        captured["env"] = dict(kwargs.get("env") or {})
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(kb, "_resolve_hermes_argv", lambda: ["hermes"])
    monkeypatch.delenv("HERMES_MAX_ITERATIONS", raising=False)

    workspace = tmp_path / "ws2"
    workspace.mkdir()
    task = _minimal_task()
    kb._default_spawn(task, str(workspace))

    assert "HERMES_MAX_ITERATIONS" not in captured["env"]
