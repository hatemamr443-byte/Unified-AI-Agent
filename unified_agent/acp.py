from __future__ import annotations

import json
import os
import queue
import signal
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Sequence

from .models import Task


class ACPWorkerError(RuntimeError):
    pass


@dataclass
class _ACPProcess:
    process: subprocess.Popen[str]
    messages: "queue.Queue[dict[str, Any]]"
    reader: threading.Thread


class ACPProcessWorker:
    """ACP v1 client for agent runtimes exposed over JSON-RPC/stdio."""

    def __init__(
        self,
        worker_id: str,
        capabilities: list[str],
        command: Sequence[str],
        *,
        timeout_seconds: float = 300,
        result_grace_seconds: float = 0.25,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        if not command:
            raise ValueError("command must not be empty")
        self.id = worker_id
        self.capabilities = list(capabilities)
        self.command = tuple(command)
        self.timeout_seconds = timeout_seconds
        self.result_grace_seconds = max(0.0, result_grace_seconds)
        self.cwd = cwd
        self.env = dict(env) if env is not None else None
        self._states: dict[str, str] = {}

    def is_available(self) -> bool:
        executable = self.command[0]
        if os.path.dirname(executable):
            return os.path.isfile(executable) and os.access(executable, os.X_OK)
        return shutil.which(executable) is not None

    def execute(self, task: Task, capability_id: str, context: Any = None) -> dict[str, Any]:
        if capability_id not in self.capabilities:
            raise ACPWorkerError(f"Worker does not support capability: {capability_id}")
        self._states[task.task_id] = "running"
        self._last_text_parts = []
        self._last_thought_parts = []
        proc: _ACPProcess | None = None
        try:
            proc = self._start_process(task)
            init = self._request(
                proc,
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {
                        "fs": {"readTextFile": False, "writeTextFile": False},
                        "terminal": False,
                        "auth": {"terminal": False},
                    },
                    "clientInfo": {"name": "unified-ai-agent", "version": "0.1.0"},
                },
                deadline=time.monotonic() + self.timeout_seconds,
            )
            if int(init.get("protocolVersion", 1)) != 1:
                raise ACPWorkerError(f"Unsupported ACP protocol version: {init.get('protocolVersion')!r}")

            agent_capabilities = init.get("agentCapabilities") or {}
            session_id = str(task.state.get("acp_session_id") or "")
            if session_id and self._supports_resume(agent_capabilities):
                self._request(
                    proc,
                    "session/resume",
                    {"sessionId": session_id, "cwd": self._session_cwd(task), "mcpServers": []},
                    deadline=time.monotonic() + self.timeout_seconds,
                )
            elif session_id and agent_capabilities.get("loadSession"):
                self._request(
                    proc,
                    "session/load",
                    {"sessionId": session_id, "cwd": self._session_cwd(task), "mcpServers": []},
                    deadline=time.monotonic() + self.timeout_seconds,
                )
            else:
                session = self._request(
                    proc,
                    "session/new",
                    {"cwd": self._session_cwd(task), "mcpServers": []},
                    deadline=time.monotonic() + self.timeout_seconds,
                )
                session_id = str(session.get("sessionId") or "")
                if not session_id:
                    raise ACPWorkerError("ACP session/new returned no sessionId")
                task.state["acp_session_id"] = session_id

            prompt = self._request(
                proc,
                "session/prompt",
                {"sessionId": session_id, "prompt": [{"type": "text", "text": self._prompt(task)}]},
                deadline=time.monotonic() + self.timeout_seconds,
                collect_updates=True,
            )
            text_parts = list(getattr(self, "_last_text_parts", []))
            thought_parts = list(getattr(self, "_last_thought_parts", []))
            if not text_parts:
                raise ACPWorkerError(
                    f"ACP agent returned no assistant text (stopReason={prompt.get('stopReason')!r})"
                )
            self._states[task.task_id] = "completed"
            return {
                "answer": "".join(text_parts),
                "stop_reason": prompt.get("stopReason"),
                "acp_session_id": session_id,
                "thought": "".join(thought_parts),
            }
        except Exception:
            self._states[task.task_id] = "failed"
            raise
        finally:
            if proc is not None:
                self._close_process(proc)

    def cancel(self, task_id: str) -> None:
        self._states[task_id] = "cancelled"

    def status(self, task_id: str) -> str:
        return self._states.get(task_id, "unknown")

    def resume(self, task: Task) -> dict[str, Any]:
        return self.execute(task, task.requested_capabilities[0])

    def _start_process(self, task: Task) -> _ACPProcess:
        environment = os.environ.copy()
        if self.env:
            environment.update(self.env)
        process = subprocess.Popen(
            list(self.command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            cwd=self.cwd or task.state.get("cwd"),
            env=environment,
            shell=False,
            start_new_session=(os.name != "nt"),
        )
        messages: "queue.Queue[dict[str, Any]]" = queue.Queue()

        def reader() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    messages.put(value)
            messages.put({"_transport_eof": True})

        thread = threading.Thread(target=reader, name=f"acp-reader-{self.id}", daemon=True)
        thread.start()
        return _ACPProcess(process, messages, thread)

    def _request(
        self,
        proc: _ACPProcess,
        method: str,
        params: dict[str, Any],
        *,
        deadline: float,
        collect_updates: bool = False,
    ) -> dict[str, Any]:
        request_id = f"unified-{time.monotonic_ns()}"
        self._send(proc, {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        text_parts: list[str] = []
        thought_parts: list[str] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._terminate(proc.process)
                raise ACPWorkerError(f"ACP request timed out: {method}")
            try:
                message = proc.messages.get(timeout=min(remaining, 0.25))
            except queue.Empty:
                continue
            if message.get("_transport_eof"):
                raise ACPWorkerError(f"ACP process exited while waiting for {method}")
            if message.get("method") == "session/update":
                self._collect_update(message, text_parts, thought_parts)
                continue
            if message.get("method") == "session/request_permission":
                self._send(
                    proc,
                    {"jsonrpc": "2.0", "id": message.get("id"), "result": {"outcome": {"outcome": "cancelled"}}},
                )
                continue
            if message.get("method"):
                if message.get("id") is not None:
                    self._send(
                        proc,
                        {
                            "jsonrpc": "2.0",
                            "id": message["id"],
                            "error": {"code": -32601, "message": f"Unsupported client method: {message['method']}"},
                        },
                    )
                continue
            if str(message.get("id")) != request_id:
                continue
            if "error" in message:
                error = message["error"] or {}
                raise ACPWorkerError(f"ACP {method} failed: {error.get('message', error)}")
            result = message.get("result") or {}
            if collect_updates:
                grace_deadline = time.monotonic() + self.result_grace_seconds
                while time.monotonic() < grace_deadline:
                    try:
                        late = proc.messages.get(timeout=max(0.0, grace_deadline - time.monotonic()))
                    except queue.Empty:
                        break
                    if late.get("method") == "session/update":
                        self._collect_update(late, text_parts, thought_parts)
                    elif late.get("method") == "session/request_permission":
                        self._send(
                            proc,
                            {"jsonrpc": "2.0", "id": late.get("id"), "result": {"outcome": {"outcome": "cancelled"}}},
                        )
                self._last_text_parts = text_parts
                self._last_thought_parts = thought_parts
            return result

    @staticmethod
    def _collect_update(message: dict[str, Any], text_parts: list[str], thought_parts: list[str]) -> None:
        update = (message.get("params") or {}).get("update") or {}
        kind = update.get("sessionUpdate")
        content = update.get("content") or {}
        text = content.get("text") if isinstance(content, dict) else None
        if not isinstance(text, str):
            return
        if kind == "agent_message_chunk":
            text_parts.append(text)
        elif kind == "agent_thought_chunk":
            thought_parts.append(text)

    @staticmethod
    def _send(proc: _ACPProcess, message: dict[str, Any]) -> None:
        if proc.process.stdin is None:
            raise ACPWorkerError("ACP stdin is unavailable")
        proc.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        proc.process.stdin.flush()

    @staticmethod
    def _supports_resume(capabilities: dict[str, Any]) -> bool:
        return bool((capabilities.get("sessionCapabilities") or {}).get("resume"))

    @staticmethod
    def _session_cwd(task: Task) -> str:
        return os.path.abspath(str(task.state.get("cwd") or os.getcwd()))

    @staticmethod
    def _prompt(task: Task) -> str:
        if task.constraints:
            constraints = json.dumps(task.constraints, ensure_ascii=False, sort_keys=True)
            return f"{task.goal}\n\nConstraints:\n{constraints}"
        return task.goal

    def _close_process(self, proc: _ACPProcess) -> None:
        if proc.process.poll() is None:
            self._terminate(proc.process)
        try:
            proc.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.process.kill()

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
            else:
                process.terminate()
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    process.kill()
        except ProcessLookupError:
            pass


class HermesACPWorker(ACPProcessWorker):
    """Hermes Agent ACP worker using the hermes acp entrypoint."""

    def __init__(
        self,
        *,
        capabilities: list[str] | None = None,
        command: Sequence[str] = ("hermes", "acp"),
        **kwargs: Any,
    ) -> None:
        super().__init__(
            "hermes-acp",
            capabilities or ["research", "coding", "browser", "terminal"],
            command,
            **kwargs,
        )
