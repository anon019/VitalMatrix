"""Regression checks for subprocess cleanup and bounded queue waits."""
import asyncio
import sys

import pytest

from app.ai.codex_cli import CodexCLIError, CodexCLIRunner


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_deadline_and_cancellation_reap_child(monkeypatch, tmp_path, cancel):
    runner = CodexCLIRunner()
    monkeypatch.setattr(runner, "_resolve_command", lambda: sys.executable)
    original_spawn = asyncio.create_subprocess_exec
    processes = []

    async def spawn(*args, **kwargs):
        process = await original_spawn(
            sys.executable, "-c", "import time; time.sleep(30)", **kwargs
        )
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    task = asyncio.create_task(runner._execute(
        prompt="test", workdir=tmp_path, output_path=tmp_path / "response.txt",
        timeout_seconds=30 if cancel else 0.05,
    ))
    while not processes:
        await asyncio.sleep(0.001)
    if cancel:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else CodexCLIError):
        await task
    assert processes[0].returncode is not None


@pytest.mark.asyncio
async def test_queue_timeout_does_not_start_work_or_leak_capacity():
    runner = CodexCLIRunner()
    runner._semaphore = asyncio.Semaphore(1)
    async with runner._semaphore:
        with pytest.raises(CodexCLIError):
            async with runner._slot(0.01):
                pytest.fail("Work must not start while the slot is occupied")
    async with runner._slot(1):
        assert runner._semaphore.locked()
