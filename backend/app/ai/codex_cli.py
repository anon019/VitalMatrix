"""Safe, isolated Codex CLI adapter for backend AI workloads."""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import signal
import shutil
import tempfile
import time
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any, Iterable

from app.config import settings

logger = logging.getLogger(__name__)


class CodexCLIError(RuntimeError):
    """Raised when a non-interactive Codex run cannot produce a usable result."""


class CodexCLIRunner:
    """Run Codex in ephemeral per-request workspaces.

    Text and vision jobs are read-only and ignore user customization. Image
    generation keeps the installed Codex skills enabled, but may only write in
    its temporary workspace.
    """

    def __init__(self) -> None:
        self.command = settings.CODEX_CLI_PATH
        self.model = settings.CODEX_MODEL
        self.reasoning_effort = settings.CODEX_REASONING_EFFORT
        self._semaphore = asyncio.Semaphore(settings.CODEX_MAX_CONCURRENCY)

    @asynccontextmanager
    async def _slot(self, timeout_seconds: int):
        """Queueing and execution share one deadline, preventing stale jobs."""
        try:
            async with asyncio.timeout(timeout_seconds):
                async with self._semaphore:
                    yield
        except TimeoutError as exc:
            raise CodexCLIError(f"Codex CLI 排队及执行超过 {timeout_seconds} 秒") from exc

    @staticmethod
    async def _stop_process(process) -> None:
        # Codex can launch tool children; terminate the isolated process group.
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except TimeoutError:
                continue
            # Kill any surviving children even if the group leader exited.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return
        await process.wait()

    def _resolve_command(self) -> str:
        resolved = shutil.which(self.command)
        if not resolved:
            raise CodexCLIError(f"Codex CLI 不可用: {self.command}")
        return resolved

    @classmethod
    def _strict_schema(cls, schema: dict[str, Any]) -> dict[str, Any]:
        """Adapt application schemas to Codex structured-output requirements."""
        normalized = copy.deepcopy(schema)

        def visit(node: Any) -> None:
            if isinstance(node, dict):
                if node.get("type") == "object" or "properties" in node:
                    properties = node.get("properties") or {}
                    node["additionalProperties"] = False
                    # Strict structured outputs require every declared property.
                    # Application schemas use empty strings/arrays/zero for fields
                    # that cannot be estimated from a particular image.
                    node["required"] = list(properties)
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)

        visit(normalized)
        return normalized

    async def _execute(
        self,
        *,
        prompt: str,
        workdir: Path,
        image_paths: Iterable[str | Path] = (),
        output_schema_path: Path | None = None,
        output_path: Path,
        timeout_seconds: int,
        reasoning_effort: str | None = None,
        enable_skills: bool = False,
        sandbox: str = "read-only",
    ) -> str:
        effective_effort = reasoning_effort or self.reasoning_effort
        command = [
            self._resolve_command(),
            "exec",
            "-",
            "--ephemeral",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--color",
            "never",
            "--sandbox",
            sandbox,
            "--cd",
            str(workdir),
            "--model",
            self.model,
            "--config",
            f'model_reasoning_effort="{effective_effort}"',
            "--output-last-message",
            str(output_path),
        ]
        if not enable_skills:
            command.append("--ignore-user-config")
        if output_schema_path is not None:
            command.extend(["--output-schema", str(output_schema_path)])

        paths = [str(Path(path).resolve()) for path in image_paths]
        if paths:
            command.append("--image")
            command.extend(paths)

        env = os.environ.copy()
        env["NO_COLOR"] = "1"
        started_at = time.perf_counter()
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(prompt.encode("utf-8")),
                timeout=timeout_seconds,
            )
        except TimeoutError as exc:
            await self._stop_process(process)
            raise CodexCLIError(f"Codex CLI 调用超过 {timeout_seconds} 秒") from exc
        except asyncio.CancelledError:
            await self._stop_process(process)
            raise

        duration_ms = (time.perf_counter() - started_at) * 1000
        if process.returncode != 0:
            diagnostic = (stderr or stdout).decode("utf-8", errors="replace")
            # CLI diagnostics may echo health prompts. Prefer explicit error
            # lines and never log the complete subprocess transcript.
            lines = [line.strip() for line in diagnostic.splitlines() if line.strip()]
            error_lines = [
                line for line in lines
                if line.lower().startswith(("error", "failed"))
                or line.startswith('"message":')
            ]
            final_line = (error_lines or ["Codex CLI execution failed"])[-1]
            raise CodexCLIError(
                f"Codex CLI 退出码 {process.returncode}: {final_line[:300]}"
            )
        if not output_path.is_file():
            raise CodexCLIError("Codex CLI 未生成最终输出文件")

        result = output_path.read_text(encoding="utf-8").strip()
        if not result:
            raise CodexCLIError("Codex CLI 返回空内容")
        logger.info(
            "Codex CLI completed: model=%s effort=%s images=%s duration_ms=%.1f",
            self.model,
            effective_effort,
            len(paths),
            duration_ms,
        )
        return result

    async def run_text(
        self,
        prompt: str,
        *,
        image_paths: Iterable[str | Path] = (),
        timeout_seconds: int | None = None,
        reasoning_effort: str | None = None,
    ) -> str:
        async with self._slot(timeout_seconds or settings.CODEX_REQUEST_TIMEOUT_SECONDS):
            with tempfile.TemporaryDirectory(prefix="health-codex-") as directory:
                workdir = Path(directory)
                return await self._execute(
                    prompt=prompt,
                    workdir=workdir,
                    image_paths=image_paths,
                    output_path=workdir / "response.txt",
                    timeout_seconds=timeout_seconds or settings.CODEX_REQUEST_TIMEOUT_SECONDS,
                    reasoning_effort=reasoning_effort,
                )

    async def run_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        image_paths: Iterable[str | Path] = (),
        timeout_seconds: int | None = None,
        reasoning_effort: str | None = None,
    ) -> dict[str, Any]:
        async with self._slot(timeout_seconds or settings.CODEX_REQUEST_TIMEOUT_SECONDS):
            with tempfile.TemporaryDirectory(prefix="health-codex-") as directory:
                workdir = Path(directory)
                schema_path = workdir / "response.schema.json"
                schema_path.write_text(
                    json.dumps(self._strict_schema(schema), ensure_ascii=False),
                    encoding="utf-8",
                )
                raw = await self._execute(
                    prompt=prompt,
                    workdir=workdir,
                    image_paths=image_paths,
                    output_schema_path=schema_path,
                    output_path=workdir / "response.json",
                    timeout_seconds=timeout_seconds or settings.CODEX_REQUEST_TIMEOUT_SECONDS,
                    reasoning_effort=reasoning_effort,
                )
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CodexCLIError(f"Codex CLI 返回的 JSON 无法解析: {exc}") from exc
        if not isinstance(value, dict):
            raise CodexCLIError("Codex CLI 返回的结构不是 JSON 对象")
        return value

    async def generate_image(
        self,
        prompt: str,
        *,
        reference_image_bytes: bytes,
        timeout_seconds: int | None = None,
    ) -> bytes:
        """Ask Luna to invoke Codex's built-in latest GPT Image tool."""
        async with self._slot(timeout_seconds or settings.POSTER_REQUEST_TIMEOUT_SECONDS):
            with tempfile.TemporaryDirectory(prefix="health-codex-image-") as directory:
                workdir = Path(directory)
                reference_path = workdir / "reference.jpg"
                reference_path.write_bytes(reference_image_bytes)
                result_path = workdir / "generated_poster.png"
                final_prompt = f"""Use the installed image generation skill and its built-in image tool.
The current required image model is {settings.CODEX_IMAGE_MODEL} (latest GPT Image).
Use the attached image as the reference/edit target. Create exactly one final PNG.
Save or copy the generated bitmap to this exact path: {result_path}
Do not run unrelated commands, inspect other files, browse the web, or modify the reference image.
Do not finish until the exact output path exists.

Image specification:
{prompt}
"""
                await self._execute(
                    prompt=final_prompt,
                    workdir=workdir,
                    image_paths=[reference_path],
                    output_path=workdir / "agent-result.txt",
                    timeout_seconds=timeout_seconds or settings.POSTER_REQUEST_TIMEOUT_SECONDS,
                    reasoning_effort=settings.CODEX_IMAGE_AGENT_REASONING_EFFORT,
                    enable_skills=True,
                    sandbox="workspace-write",
                )
                if not result_path.is_file():
                    raise CodexCLIError("Codex 图片任务未生成指定的海报底图")
                return result_path.read_bytes()


_runner: CodexCLIRunner | None = None


def get_codex_cli_runner() -> CodexCLIRunner:
    global _runner
    if _runner is None:
        _runner = CodexCLIRunner()
    return _runner
