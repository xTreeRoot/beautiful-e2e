# Codex 桥接与 MySQL

## 可插拔 AI 供应商

Beautiful E2E 现在把 Codex 供应商 HTTP 桥接核心代码内置在：

```text
backend/app/services/ai/codex_http_bridge.py
backend/app/services/ai/codex_bridge.py
backend/app/services/ai/codex_exec.py
backend/app/services/ai/case_completion.py
```

后端运行时不再依赖外部 `codex-provider-http-bridge` 项目。
它会通过 `backend/app/services/ai` 中的抽象 AI 网关调用内置供应商。

内置供应商：

- `codex_exec`：默认供应商，直接调用本机 `codex exec` 执行 AI 生成。
- `rule_based`：确定性的本地脚手架生成器。
- `codex_bridge`：GPT/OpenAI 兼容 HTTP 供应商，可复用 Codex 本地配置。
- `openai_compatible`：自定义 OpenAI 兼容 HTTP 供应商，适配通用互联网模型网关。

可通过以下方式加载自定义供应商：

```bash
AI_PROVIDER_ENTRYPOINT=my_package.my_provider:create_provider
```

工厂函数接收后端 `Settings` 对象，并必须返回带以下成员的供应商：

```python
name: str
generate(context: CaseGenerationContext) -> GeneratedCase
```

## Codex Exec

默认模式是：

```bash
AI_PROVIDER=codex_exec
```

后端会调用本机 `codex exec`，默认不额外追加 `--sandbox` 或 `--ephemeral`，
因此执行策略会跟随本机 Codex 配置；需要覆盖时可通过工作台“AI 配置”弹窗或环境变量显式设置。
最终结构化结果仍通过 `--output-last-message` 读取。用例生成提示词、payload、返回解析都在
`case_completion.py`，`codex_exec.py` 只负责 CLI 调用。

可选配置：

```bash
CODEX_EXEC_COMMAND=codex
CODEX_EXEC_MODEL=
CODEX_EXEC_PROFILE=
CODEX_EXEC_PROFILE_V2=
CODEX_EXEC_CWD=
CODEX_EXEC_SANDBOX=workspace-write
CODEX_EXEC_EPHEMERAL=false
CODEX_EXEC_IMAGE_PATHS='["/path/to/reference.png"]'
CODEX_EXEC_ADD_DIRS='["/path/to/shared"]'
CODEX_EXEC_CONFIG_OVERRIDES='["model_reasoning_effort=\"high\""]'
```

系统已透传 `codex exec` 的常用非交互能力：`--config`、`--enable`、`--disable`、
`--strict-config`、`--model`、`--oss`、`--local-provider`、`--profile`、
`--profile-v2`、`--sandbox`、`--cd`、`--add-dir`、`--skip-git-repo-check`、
`--ephemeral`、`--ignore-user-config`、`--ignore-rules`、`--output-schema`、
`--json` 和 `--output-last-message`。其中 `--json` 会返回 JSONL 事件流；后端只转发
Codex CLI 明确暴露的 reasoning/content 增量。如果 CLI 只返回
`reasoning_output_tokens` 计数，没有返回推理文本，前端只展示平台等待进度，不伪造推理内容。

## Codex 供应商 HTTP 桥接

HTTP 桥接不会自动操作 Codex 桌面界面。
内置桥接按以下优先级读取供应商配置：

1. `AI_API_KEY` / `AI_BASE_URL` 或 `AI_PROVIDER_CONFIG`。
2. `OPENAI_API_KEY` / `OPENAI_BASE_URL`。
3. `CODEX_HOME` 或 `~/.codex`：

- `~/.codex/auth.json`
- `~/.codex/config.toml`

生成成功后，持久化用例会保存：

```json
{
  "generation_mode": "codex_exec"
}
```

当 `AI_PROVIDER=codex_bridge` 或 `AI_PROVIDER=openai_compatible` 时，生成接口会优先用供应商 SSE 获取增量。
后端会把供应商显式返回的 `reasoning_content`、reasoning summary 和输出文本转换成
`provider_delta` 事件；如果当前供应商不返回思考增量，则只展示输出增量和平台阶段消息。
HTTP 桥接会先压缩仓库摘要、引用文档和画布 DSL，尽量保留接口路径、方法、字段和变量链路证据；
如果供应商返回上下文超限，会自动使用更严格预算重试一次。
当 `AI_PROVIDER=codex_exec` 时，后端会调用 `codex exec --json` 并转发 Codex CLI 暴露的
reasoning/content JSONL 事件；最终结构化 JSON 仍以 `--output-last-message` 文件为准。

如果供应商失败且 `AI_FALLBACK_RULE_BASED=true`，后端会回退到确定性脚手架生成器，并把错误记录到 `code_context.ai_provider_error`。

常用供应商检查：

```bash
curl http://127.0.0.1:8000/api/ai/provider
```

工作台项目面板的“AI 配置”弹窗也会读取这个接口，展示 `codex_exec`、GPT HTTP 桥接、OpenAI 兼容自定义和规则生成器的可用状态。保存时会写入数据库表 `ai_provider_configs`，并持久化“项目分析”“Prompt 生成 DSL”“接口运行辅助测试”的用途规划；同一个供应商可以绑定多个用途。

## 本机 MySQL

本地数据库是：

```text
beautiful_e2e
```

后端启动时会通过 SQLAlchemy `create_all` 自动创建结构。

常用检查：

```bash
curl http://127.0.0.1:8000/api/ai/provider
curl -X POST http://127.0.0.1:8000/api/bootstrap
MYSQL_PWD='******' mysql -uroot beautiful_e2e -e "SHOW TABLES;"
```
