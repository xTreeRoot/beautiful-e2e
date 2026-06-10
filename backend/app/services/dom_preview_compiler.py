from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from app.core.config import Settings
from app.services.ai import build_case_generation_provider
from app.services.ai.base import CaseGenerationError
from app.services.ai_settings import AI_USAGE_DOM_COMPILATION
from app.services.dom_project_analyzer import PAGE_CONFIG_NAMES


VIEW_SOURCE_EXTENSIONS = (
    ".vue",
    ".nvue",
    ".tsx",
    ".jsx",
    ".wxml",
    ".axml",
    ".svelte",
    ".html",
    ".js",
    ".ts",
)


class DomCompletionClient(Protocol):
    def complete(self, system: str, prompt: str) -> str:
        """调用 AI 文本补全并返回最终文本。"""


class DomPreviewCompilationError(RuntimeError):
    """DOM 预览编译失败时抛出，API 层会转换成可读错误。"""


@dataclass(frozen=True)
class DomModuleSource:
    source_file: str
    source_text: str
    source_files: list[str]


def compile_dom_module_preview(
    module: dict[str, Any],
    *,
    source_text: str,
    settings: Settings,
    client: DomCompletionClient | None = None,
) -> dict[str, Any]:
    """使用 DOM 页面编译/修复用途的 AI，把源码证据补全为系统内预览 HTML。

    返回值只更新 `preview` 字段；调用方负责把它写回项目索引。HTML 会放入
    sandbox iframe，提示词也要求不生成脚本和外链，降低预览阶段的副作用。
    """

    completion_client = client or _client_from_settings(settings)
    try:
        raw = completion_client.complete(
            system=_compile_system_prompt(),
            prompt=json.dumps(_compile_payload(module, source_text), ensure_ascii=False),
        )
    except CaseGenerationError as exc:
        raise DomPreviewCompilationError(_safe_ai_error_message(str(exc))) from exc
    parsed = _json_from_model_text(raw)
    html = str(parsed.get("html") or "").strip()
    if not html:
        raise DomPreviewCompilationError("DOM 页面编译/修复 AI 未返回 html 字段")

    warnings = parsed.get("warnings")
    warning_items = (
        [str(item).strip() for item in warnings if str(item).strip()]
        if isinstance(warnings, list)
        else []
    )
    return {
        "strategy": "ai_dom_compilation",
        "ai_usage_key": AI_USAGE_DOM_COMPILATION,
        "html": _ensure_document_html(html),
        "warnings": warning_items[:8],
        "compiled_at": datetime.now(UTC).isoformat(),
    }


def static_compile_dom_module_preview(module: dict[str, Any], *, source_text: str) -> dict[str, Any]:
    """重新执行本地静态编译，用于用户在图谱里手动刷新系统内草图。

    这一步不调用 AI，适合先把最新源码证据写进预览；如果静态编译仍然没有控件，
    前端会继续引导用户使用 DOM 页面编译/修复 AI 用途。
    """

    name = str(module.get("name") or module.get("route") or module.get("source_file") or "未命名模块")
    kind = str(module.get("kind") or "component")
    route = str(module.get("route") or "").strip() or None
    hints = _source_hints(source_text)
    return {
        "strategy": "static_dom_sketch",
        "ai_usage_key": AI_USAGE_DOM_COMPILATION,
        "html": _static_preview_html(name=name, module_kind=kind, route=route, hints=hints),
        "warnings": [
            "当前预览是源码证据生成的系统内草图，不依赖被测项目前端服务。",
            "复杂页面可继续使用 DOM 页面编译/修复 AI 用途进一步补全。",
        ],
        "compiled_at": datetime.now(UTC).isoformat(),
    }


def module_compile_source(root: Path, module: dict[str, Any]) -> DomModuleSource:
    """读取用于编译的页面源码，配置文件页面会按 route 反查页面本体。

    小程序/uni-app 的 `pages.json` 只描述页面入口，真实 DOM 结构通常在
    `pages/**/index.vue`。编译阶段需要优先读页面本体，否则 AI 只能看到标题和路由。
    """

    source_file = str(module.get("source_file") or "").strip()
    if not source_file:
        raise DomPreviewCompilationError("DOM 模块缺少源码文件，无法编译")

    source_text = module_source_text(root, source_file)
    config_source_file = str(module.get("config_source_file") or "").strip()
    if config_source_file and config_source_file != source_file:
        # 新索引已把 source_file 指向真实页面；配置文件仍提供标题和路由上下文。
        config_source_text = _optional_module_source_text(root, config_source_file)
        if config_source_text is not None:
            return DomModuleSource(
                source_file=source_file,
                source_text=_combined_page_source_text(
                    page_source_file=source_file,
                    page_source_text=source_text,
                    config_source_file=config_source_file,
                    config_source_text=config_source_text,
                ),
                source_files=[config_source_file, source_file],
            )

    resolved_source_file = _route_implementation_source_file(
        root,
        config_source_file=source_file,
        route=str(module.get("route") or ""),
    )
    if not resolved_source_file or resolved_source_file == source_file:
        return DomModuleSource(source_file=source_file, source_text=source_text, source_files=[source_file])

    resolved_text = module_source_text(root, resolved_source_file)
    return DomModuleSource(
        source_file=resolved_source_file,
        source_text=_combined_page_source_text(
            page_source_file=resolved_source_file,
            page_source_text=resolved_text,
            config_source_file=source_file,
            config_source_text=source_text,
        ),
        source_files=[source_file, resolved_source_file],
    )


def _client_from_settings(settings: Settings) -> DomCompletionClient:
    # codex exec 的用例生成默认带结构化 schema；DOM 编译需要自己的 JSON 契约。
    ai_provider_config = dict(settings.ai_provider_config or {})
    ai_provider_config["output_schema_enabled"] = False
    provider_settings = settings.model_copy(
        update={
            "codex_exec_output_schema_enabled": False,
            "ai_provider_config": ai_provider_config,
        }
    )
    try:
        provider = build_case_generation_provider(provider_settings)
    except Exception as exc:
        raise DomPreviewCompilationError(f"无法加载 DOM 页面编译/修复 AI：{exc}") from exc

    client = getattr(provider, "client", None)
    if client is None or not callable(getattr(client, "complete", None)):
        raise DomPreviewCompilationError("当前 AI 供应商不支持 DOM 页面编译/修复")
    return client


def _safe_ai_error_message(raw: str) -> str:
    """压缩供应商错误，避免把 prompt、源码片段或请求头上下文透传到前端。"""

    if "Invalid schema for response_format" in raw or "invalid_json_schema" in raw:
        return "DOM 页面编译/修复 AI 的结构化输出配置冲突，已关闭用例生成 schema 后请重试。"
    if "timed out" in raw.lower() or "生成超时" in raw:
        return "DOM 页面编译/修复 AI 调用超时，请稍后重试。"
    first_line = next((line.strip() for line in raw.splitlines() if line.strip()), "")
    if not first_line:
        return "DOM 页面编译/修复 AI 调用失败"
    return f"DOM 页面编译/修复 AI 调用失败：{first_line[:160]}"


def _compile_system_prompt() -> str:
    return (
        "你是 Beautiful E2E 的 DOM 页面编译/修复器。"
        "你只根据输入的源码片段和页面证据生成一个可放入 iframe srcDoc 的静态 HTML 预览。"
        "不要访问网络，不要生成 script，不要生成外链资源，不要添加真实业务数据。"
        "最终只返回 JSON 对象，字段为 html 和 warnings。"
    )


def _compile_payload(module: dict[str, Any], source_text: str) -> dict[str, Any]:
    preview = module.get("preview") if isinstance(module.get("preview"), dict) else {}
    return {
        "contract": {
            "html": "完整 HTML 字符串，必须包含 doctype/html/head/body，可以内联少量 CSS。",
            "warnings": "字符串数组，说明无法确定或被简化的结构。",
        },
        "module": {
            "kind": module.get("kind"),
            "name": module.get("name"),
            "route": module.get("route"),
            "source": module.get("source"),
            "source_file": module.get("source_file"),
            "compile_source_file": module.get("compile_source_file"),
            "compile_source_files": module.get("compile_source_files"),
            "framework": module.get("framework"),
            "evidence": module.get("evidence") if isinstance(module.get("evidence"), list) else [],
            "current_preview_strategy": preview.get("strategy"),
        },
        "source_excerpt": source_text[:12000],
        "requirements": [
            "页面标题和主要区域要对应 module.name/module.route。",
            "把能识别的按钮、输入框、列表、卡片、导航或状态区域渲染成静态 DOM。",
            "保留 data-testid、aria-label、placeholder、name、id 等可自动化定位属性。",
            "如果源码像小程序或 uni-app，把 view/text/image/button/input 语义映射成普通 HTML 标签。",
            "不要使用脚本、远程图片、远程字体、真实 token、真实请求头或外部接口地址。",
        ],
    }


def _json_from_model_text(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        raise DomPreviewCompilationError("DOM 页面编译/修复 AI 没有返回内容")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
        if not fenced:
            object_match = re.search(r"\{.*\}", text, flags=re.S)
            if not object_match:
                raise DomPreviewCompilationError("DOM 页面编译/修复 AI 未返回 JSON 对象") from None
            text = object_match.group(0)
        else:
            text = fenced.group(1)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DomPreviewCompilationError("DOM 页面编译/修复 AI 返回的 JSON 无法解析") from exc
    if not isinstance(parsed, dict):
        raise DomPreviewCompilationError("DOM 页面编译/修复 AI 返回的 JSON 必须是对象")
    return parsed


def _ensure_document_html(html: str) -> str:
    if re.search(r"<!doctype\s+html", html, flags=re.I) and re.search(r"<html\b", html, flags=re.I):
        return html
    return (
        "<!doctype html>\n"
        "<html lang=\"zh-CN\">\n"
        "<head><meta charset=\"utf-8\" /><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" /></head>\n"
        f"<body>{html}</body>\n"
        "</html>"
    )


def _source_hints(source_text: str) -> list[str]:
    hints: list[str] = []
    for raw_line in source_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(
            token in line
            for token in ["data-testid", "aria-label", "placeholder", "<button", "<input", "<form", "bindtap"]
        ):
            hints.append(line[:160])
        if len(hints) >= 12:
            break
    return hints


def _static_preview_html(
    *,
    name: str,
    module_kind: str,
    route: str | None,
    hints: list[str],
) -> str:
    title = _escape_html(name or "未命名页面")
    subtitle = "页面模块" if module_kind == "page" else "组件模块"
    route_label = _escape_html(route or "无页面路由")
    hint_cards = "\n".join(_static_hint_card(hint) for hint in hints[:8])
    if not hint_cards:
        hint_cards = "<p class=\"empty\">静态编译未提取到控件，可点击 AI 修复编译补全页面结构。</p>"
    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <style>
    body {{ margin: 0; background: #f7f6f2; color: #222833; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ min-height: 100vh; padding: 18px; }}
    header {{ border: 1px solid #d8eee7; border-radius: 8px; background: #eef8f5; padding: 14px; }}
    h1 {{ margin: 0 0 6px; font-size: 20px; line-height: 1.25; }}
    .meta {{ color: #746f65; font-size: 12px; }}
    .grid {{ display: grid; gap: 10px; margin-top: 14px; }}
    .card {{ border: 1px solid #eee8dc; border-radius: 8px; background: #fffefa; padding: 12px; }}
    .label {{ color: #6b6257; font-size: 12px; font-weight: 800; }}
    .hint {{ margin-top: 6px; color: #333a45; font-family: SFMono-Regular, Consolas, monospace; font-size: 12px; white-space: pre-wrap; word-break: break-word; }}
    .empty {{ margin: 0; color: #746f65; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{title}</h1>
      <div class=\"meta\">{subtitle} · {route_label} · 系统内静态 DOM 草图</div>
    </header>
    <section class=\"grid\">{hint_cards}</section>
  </main>
</body>
</html>"""


def _static_hint_card(hint: str) -> str:
    return (
        "<article class=\"card\">"
        "<div class=\"label\">DOM 证据</div>"
        f"<div class=\"hint\">{_escape_html(hint)}</div>"
        "</article>"
    )


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def module_source_text(root: Path, source_file: str) -> str:
    """读取模块源码，限制在仓库根目录内，避免通过 source_file 越界读取。"""

    root_path = root.expanduser().resolve()
    source_path = (root_path / source_file).resolve()
    try:
        source_path.relative_to(root_path)
    except ValueError as exc:
        raise DomPreviewCompilationError("DOM 模块源码路径不在仓库目录内") from exc
    if not source_path.exists() or not source_path.is_file():
        raise DomPreviewCompilationError("DOM 模块源码文件不存在")
    return source_path.read_text(encoding="utf-8", errors="ignore")


def _optional_module_source_text(root: Path, source_file: str) -> str | None:
    try:
        return module_source_text(root, source_file)
    except DomPreviewCompilationError:
        return None


def _route_implementation_source_file(
    root: Path,
    *,
    config_source_file: str,
    route: str,
) -> str | None:
    if Path(config_source_file).name not in PAGE_CONFIG_NAMES or not route.strip():
        return None

    root_path = root.expanduser().resolve()
    config_path = (root_path / config_source_file).resolve()
    try:
        config_path.relative_to(root_path)
    except ValueError:
        return None

    route_stems = _route_source_stems(route)
    for base in _candidate_source_bases(root_path, config_path.parent):
        for stem in route_stems:
            for extension in VIEW_SOURCE_EXTENSIONS:
                candidate = (base / f"{stem}{extension}").resolve()
                relative = _relative_source_file(root_path, candidate)
                if relative and candidate.is_file():
                    return relative
    return None


def _candidate_source_bases(root_path: Path, config_dir: Path) -> list[Path]:
    bases: list[Path] = []
    for base in [config_dir, config_dir / "src", root_path, root_path / "src"]:
        resolved = base.resolve()
        if resolved not in bases:
            bases.append(resolved)
    return bases


def _route_source_stems(route: str) -> list[str]:
    normalized = route.split("?", 1)[0].split("#", 1)[0].strip().strip("/")
    if not normalized:
        return []

    stems = [normalized]
    if not normalized.endswith("/index"):
        stems.append(f"{normalized}/index")
    if not normalized.startswith("pages/"):
        stems.append(f"pages/{normalized}")
        if not normalized.endswith("/index"):
            stems.append(f"pages/{normalized}/index")
    return _unique_strings(stems)


def _relative_source_file(root_path: Path, candidate: Path) -> str | None:
    try:
        return candidate.relative_to(root_path).as_posix()
    except ValueError:
        return None


def _combined_page_source_text(
    *,
    page_source_file: str,
    page_source_text: str,
    config_source_file: str,
    config_source_text: str,
) -> str:
    config_excerpt = config_source_text[:3000]
    return (
        f"// 页面源码：{page_source_file}\n"
        f"{page_source_text}\n\n"
        f"// 页面路由配置：{config_source_file}\n"
        f"{config_excerpt}"
    )


def _unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
