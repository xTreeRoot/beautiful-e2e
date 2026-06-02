from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Iterator
from urllib import error, request


@dataclass(frozen=True)
class CodexHttpBridgeConfig:
    """OpenAI 兼容 HTTP 调用的连接配置。

    显式传入的 `api_key` 和 `base_url` 优先，其次读取环境变量，最后读取
    本地 Codex 配置目录。这样既对齐独立桥接脚本，也能被应用直接导入。
    """

    model: str
    wire_api: str = "responses"
    api_key: str | None = None
    base_url: str | None = None
    codex_home: Path | None = None
    reasoning_effort: str | None = "xhigh"
    timeout_seconds: int = 180
    max_tokens: int = 3000
    temperature: float | None = None


class CodexHttpBridgeError(RuntimeError):
    pass


class CodexProviderHttpBridge:
    """复用 Codex/OpenAI 兼容供应商配置的直接 HTTP 桥接。"""

    def __init__(self, config: CodexHttpBridgeConfig) -> None:
        self.config = config

    def complete(self, system: str, prompt: str) -> str:
        api_key, base_url = resolve_settings(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            codex_home_path=self.config.codex_home,
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        if self.config.wire_api == "chat":
            return run_chat(messages, self.config, api_key, base_url)
        if self.config.wire_api == "responses":
            return run_responses(messages, self.config, api_key, base_url)
        raise CodexHttpBridgeError(f"不支持的传输 API：{self.config.wire_api}")

    def stream_complete(self, system: str, prompt: str) -> Iterator[dict[str, Any]]:
        api_key, base_url = resolve_settings(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            codex_home_path=self.config.codex_home,
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        if self.config.wire_api == "chat":
            yield from run_chat_stream(messages, self.config, api_key, base_url)
            return
        if self.config.wire_api == "responses":
            yield from run_responses_stream(messages, self.config, api_key, base_url)
            return
        raise CodexHttpBridgeError(f"不支持的传输 API：{self.config.wire_api}")


def codex_home(path: Path | None = None) -> Path:
    if path is not None:
        return path.expanduser()
    env_home = os.getenv("CODEX_HOME")
    return Path(env_home).expanduser() if env_home else Path.home() / ".codex"


def read_auth_api_key(home: Path) -> str | None:
    path = home / "auth.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    value = data.get("OPENAI_API_KEY")
    return value.strip() if isinstance(value, str) and value.strip() else None


def match_toml_key(block: str, key: str) -> str | None:
    match = re.search(rf'(?m)^\s*{re.escape(key)}\s*=\s*"([^"]+)"\s*$', block)
    return match.group(1) if match else None


def read_provider_base_url(home: Path) -> str | None:
    path = home / "config.toml"
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    provider = match_toml_key(text, "model_provider")
    if not provider:
        return None
    section = re.search(rf"(?ms)^\[model_providers\.{re.escape(provider)}\]\s*(.*?)(?=^\[|\Z)", text)
    if not section:
        return None
    return match_toml_key(section.group(1), "base_url")


def normalize_base_url(base_url: str) -> str:
    trimmed = base_url.strip().rstrip("/")
    if not trimmed:
        raise CodexHttpBridgeError("基础地址为空")
    if re.match(r"^https?://[^/]+$", trimmed):
        return trimmed + "/v1"
    return trimmed


def resolve_settings(
    *,
    api_key: str | None,
    base_url: str | None,
    codex_home_path: Path | None,
) -> tuple[str, str]:
    home = codex_home(codex_home_path)
    resolved_key = api_key or os.getenv("OPENAI_API_KEY") or read_auth_api_key(home)
    resolved_base_url = base_url or os.getenv("OPENAI_BASE_URL") or read_provider_base_url(home)
    if not resolved_key:
        raise CodexHttpBridgeError(
            "缺少 API 密钥；请设置 AI_API_KEY/OPENAI_API_KEY，或配置 Codex auth.json"
        )
    if not resolved_base_url:
        raise CodexHttpBridgeError(
            "缺少基础地址；请设置 AI_BASE_URL/OPENAI_BASE_URL，或配置 Codex config.toml"
        )
    return resolved_key, normalize_base_url(resolved_base_url)


def post_json(
    url: str,
    api_key: str,
    payload: dict[str, Any],
    accept: str,
    timeout_seconds: int,
) -> Iterable[str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": accept,
            "User-Agent": "beautiful-e2e-codex-provider-http-bridge/1.0",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            for raw_line in resp:
                yield raw_line.decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise CodexHttpBridgeError(f"HTTP {exc.code}: {detail}") from exc
    except OSError as exc:
        raise CodexHttpBridgeError(str(exc)) from exc


def event_payloads(lines: Iterable[str]) -> Iterable[str]:
    data_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip("\n\r")
        if not line:
            if data_lines:
                payload = "\n".join(data_lines).strip()
                data_lines.clear()
                if payload and payload != "[DONE]":
                    yield payload
            continue
        if line.lstrip().startswith("data:"):
            data_lines.append(line.split("data:", 1)[1].lstrip())
    if data_lines:
        payload = "\n".join(data_lines).strip()
        if payload and payload != "[DONE]":
            yield payload


def response_payloads(lines: Iterable[str]) -> Iterable[str]:
    collected = list(lines)
    joined = "".join(collected).lstrip()
    if joined.startswith("data:") or joined.startswith("event:"):
        return event_payloads(collected)
    return iter([joined])


def extract_responses_text(obj: dict[str, Any]) -> str:
    output_text = obj.get("output_text")
    if isinstance(output_text, str):
        return output_text
    output = obj.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        text = part.get("text") or part.get("output_text")
                        if isinstance(text, str):
                            chunks.append(text)
            text = item.get("text")
            if isinstance(text, str):
                chunks.append(text)
        return "".join(chunks)
    text = obj.get("text")
    return text if isinstance(text, str) else ""


def run_chat(
    messages: list[dict[str, str]],
    config: CodexHttpBridgeConfig,
    api_key: str,
    base_url: str,
) -> str:
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "stream": False,
    }
    if config.max_tokens:
        payload["max_tokens"] = config.max_tokens
    if config.temperature is not None:
        payload["temperature"] = config.temperature

    lines = post_json(
        base_url + "/chat/completions",
        api_key,
        payload,
        "application/json",
        config.timeout_seconds,
    )
    obj = json.loads(next(response_payloads(lines)))
    return obj.get("choices", [{}])[0].get("message", {}).get("content", "")


def run_chat_stream(
    messages: list[dict[str, str]],
    config: CodexHttpBridgeConfig,
    api_key: str,
    base_url: str,
) -> Iterator[dict[str, Any]]:
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "stream": True,
    }
    if config.max_tokens:
        payload["max_tokens"] = config.max_tokens
    if config.temperature is not None:
        payload["temperature"] = config.temperature

    lines = post_json(
        base_url + "/chat/completions",
        api_key,
        payload,
        "text/event-stream",
        config.timeout_seconds,
    )
    content_chunks: list[str] = []
    for payload_text in event_payloads(lines):
        obj = json.loads(payload_text)
        if obj.get("error"):
            raise CodexHttpBridgeError(json.dumps(obj["error"], ensure_ascii=False))

        for choice in obj.get("choices", []):
            if not isinstance(choice, dict):
                continue
            delta_obj = choice.get("delta")
            if not isinstance(delta_obj, dict):
                continue

            reasoning_delta = first_string_field(
                delta_obj,
                "reasoning_content",
                "reasoning",
                "reasoning_text",
                "thinking",
            )
            if reasoning_delta:
                yield provider_delta("reasoning", reasoning_delta, obj.get("id"), "chat.delta")

            content_delta = first_string_field(delta_obj, "content", "text")
            if content_delta:
                content_chunks.append(content_delta)
                yield provider_delta("content", content_delta, obj.get("id"), "chat.delta")

    yield {"type": "provider_final", "text": "".join(content_chunks)}


def run_responses(
    messages: list[dict[str, str]],
    config: CodexHttpBridgeConfig,
    api_key: str,
    base_url: str,
) -> str:
    payload: dict[str, Any] = {
        "model": config.model,
        "input": "\n\n".join(f"{m['role']}:\n{m['content']}" for m in messages),
        "store": False,
        "stream": False,
    }
    if config.reasoning_effort:
        payload["reasoning"] = {"effort": config.reasoning_effort}
    if config.max_tokens:
        payload["max_output_tokens"] = config.max_tokens

    lines = post_json(
        base_url + "/responses",
        api_key,
        payload,
        "application/json",
        config.timeout_seconds,
    )
    fallback = ""
    for payload_text in response_payloads(lines):
        obj = json.loads(payload_text)
        typ = obj.get("type")
        if typ == "response.output_text.delta":
            fallback += obj.get("delta") if isinstance(obj.get("delta"), str) else ""
        elif typ == "response.output_text.done":
            text = obj.get("text")
            fallback = fallback or (text if isinstance(text, str) else "")
        elif typ == "response.completed":
            response_obj = obj.get("response")
            if isinstance(response_obj, dict):
                fallback = fallback or extract_responses_text(response_obj)
        elif typ in {"response.failed", "response.incomplete"}:
            raise CodexHttpBridgeError(json.dumps(obj, ensure_ascii=False))
        else:
            fallback = fallback or extract_responses_text(obj)
    return fallback


def run_responses_stream(
    messages: list[dict[str, str]],
    config: CodexHttpBridgeConfig,
    api_key: str,
    base_url: str,
) -> Iterator[dict[str, Any]]:
    payload: dict[str, Any] = {
        "model": config.model,
        "input": "\n\n".join(f"{m['role']}:\n{m['content']}" for m in messages),
        "store": False,
        "stream": True,
    }
    if config.reasoning_effort:
        payload["reasoning"] = {"effort": config.reasoning_effort}
    if config.max_tokens:
        payload["max_output_tokens"] = config.max_tokens

    lines = post_json(
        base_url + "/responses",
        api_key,
        payload,
        "text/event-stream",
        config.timeout_seconds,
    )
    content_chunks: list[str] = []
    final_text = ""
    for payload_text in event_payloads(lines):
        obj = json.loads(payload_text)
        typ = str(obj.get("type") or "")

        if typ in {"response.failed", "response.incomplete"}:
            raise CodexHttpBridgeError(json.dumps(obj, ensure_ascii=False))

        delta = first_string_field(obj, "delta", "text_delta")
        if delta:
            channel = "reasoning" if response_event_is_reasoning(typ) else "content"
            if channel == "content":
                if response_event_is_output_text(typ):
                    content_chunks.append(delta)
                elif typ:
                    yield provider_delta(
                        channel,
                        delta,
                        obj.get("response_id") or obj.get("id"),
                        typ,
                        collect=False,
                    )
                    continue
            yield provider_delta(channel, delta, obj.get("response_id") or obj.get("id"), typ)
            continue

        text = first_string_field(obj, "text", "output_text")
        if typ == "response.output_text.done" and text:
            final_text = text
        elif typ == "response.completed":
            response_obj = obj.get("response")
            if isinstance(response_obj, dict):
                final_text = extract_responses_text(response_obj) or final_text

    yield {"type": "provider_final", "text": final_text or "".join(content_chunks)}


def first_string_field(obj: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = obj.get(key)
        if isinstance(value, str):
            return value
    return ""


def response_event_is_reasoning(event_type: str) -> bool:
    lowered = event_type.lower()
    return "reasoning" in lowered or "thinking" in lowered or "summary_text" in lowered


def response_event_is_output_text(event_type: str) -> bool:
    lowered = event_type.lower()
    return not lowered or "output_text" in lowered or "message.delta" in lowered


def provider_delta(
    channel: str,
    delta: str,
    vendor_event_id: Any,
    vendor_event_type: str,
    collect: bool | None = None,
) -> dict[str, Any]:
    # 只转发供应商显式返回的增量字段，不能在本地伪造或补写模型隐藏推理。
    label = "供应商思考" if channel == "reasoning" else "供应商输出"
    return {
        "type": "provider_delta",
        "channel": channel,
        "delta": delta,
        "message": delta,
        "label": label,
        "vendor_event_id": vendor_event_id,
        "vendor_event_type": vendor_event_type,
        "collect": channel == "content" if collect is None else collect,
    }
