# Beautiful E2E

Beautiful E2E 是一个面向多人协作的端到端自动化测试平台雏形：开发同学用自然语言描述业务链路，平台读取前后端仓库代码上下文，生成可分组、可视化、可持久化、可导出为 Playwright 的回归测试用例。

## 核心能力

- 用例分组：内置核心链路组、浏览组、回归冒烟组、异常路径组，也支持自定义分组。
- 用例创建：用例库支持弹窗新建，可选择空白用例或 AI 生成，并指定分组、标题、说明和优先级；每个用例会绑定自己的 `source_prompt`。
- 自然语言生成：后端预留 LLM 生成器接口，当前提供可本地运行的规则生成器，能结合前后端仓库文件结构生成测试步骤和节点图。
- 可控制节点：前端用 React Flow 提供节点工具箱、节点拖拽、连线、属性编辑、删除、DSL 实时预览和保存。
- 智能体 / 技能：可选择不同测试智能体，并启用多个技能影响生成策略；纯后端接口模式会默认注入接口逻辑与参数推测智能体、路由约束技能和参数来源推测技能，这些上下文会传入 Codex 供应商桥接并写入用例 `code_context`。
- 执行模式开关：支持“前后端配合模式”和“纯后端接口模式”；前后端配合模式会在平台里直接运行浏览器步骤并展示截图，接口模式会动态发送请求并展示状态码、耗时、响应预览。
- 多环境配置：项目可维护本地、开发、测试、预发、生产等环境的前端/接口基础地址；接口环境还绑定请求头键值，新建、编辑和项目面板都能分别选择前端环境与接口环境。
- 路由证据约束：纯后端接口模式会扫描后端控制器 / 路由装饰器 / Swagger / OpenAPI 文档，向生成器提供真实方法、URL、处理函数、来源文件、参数、请求体和响应结构，避免凭某个业务域的惯例编造接口。
- 接口参数链路：接口步骤支持在 `step.data.extract` 中从响应 JSON 提取业务变量，并在后续 `target_url`、非认证 `data.headers`、`data.body` 中使用 `{{变量}}`；认证、登录态和网关请求头由项目请求头配置注入，不进入 DSL 变量链。生成器会倒推缺失的上游搜索、列表、详情、首页、预检或创建接口，运行器和 Playwright 导出都会真实解析变量。运行期若 JSONPath 或响应字段变动导致变量缺失，会先从前序响应做确定性别名推导，仍无法推导时可调用配置的 AI agent 做受限抽取，避免只在图上连线但 body 参数缺失。
- 生成反馈闭环：纯后端接口模式保存用例前会按真实路由目录纠正常见的 method/path/query/body 契约偏差，并把 404、未知处理器、硬编码 ID、无生产者变量等问题整理到 `code_context.api_generation_feedback`。后续把运行失败反馈给生成 agent 时，应优先回到项目路径内的路由、Swagger/OpenAPI 和 DTO 契约，而不是继续沿用失败 DSL。
- 项目分析索引：创建项目可选择立即分析，也可在工作台点击“更新分析”；重新分析会调用 `POST /api/projects/{project_id}/analyze/stream` 并通过 SSE 持续展示扫描进度、扫描覆盖率和耗时。多模块仓库会按构建子模块分组轮询扫描，并优先覆盖 Controller、路由和 OpenAPI 文件；`max_routes` 只限制最终摘要大小，不会让路径靠前的子模块独占接口名额。分析结果会写入 `repositories.index_summary`，后续生成优先复用已沉淀的接口路由和 DOM 目标；DOM 页面模块会保留源码中的组件引用，前端图谱按同仓库组件联动展示入口、目标和链路关系。
- 项目知识图谱：项目分析会把接口路由进一步归纳为模块、入口候选、适用/排除场景和变量流关系，写入 `project_knowledge_graphs`。模块名只使用主路径段，后续路径段作为子域或跨模块关联线索；工作台“项目分析中心”提供模块树、链路图、证据卡片和相似接口搜索。候选图谱是带截断提示的轻量摘要，会合并工作区与子仓库重复扫描出的同一路由模块，人工批准为 `reviewed` 后才会进入 `project_context.knowledge_graph`，作为 DSL 生成的强事实。
- MySQL 持久化：SQLAlchemy 模型覆盖项目、仓库、用户、用例组、用例、步骤、执行记录、评论和审计事件。
- Playwright 落地：可把平台用例导出为 `runner/tests/generated/*.spec.ts`，接入 CI 回归。
- 多人协作：保留创建人、评论、审计事件、执行人等协作字段，后续可接 SSO/RBAC。

## 技术栈

- 后端：Python 3.11+、FastAPI、SQLAlchemy、Pydantic。
- 数据库：MySQL 8.x，本地开发和测试均使用 MySQL。
- 前端：React、TypeScript、Vite、React Flow、Lucide Icons。
- 自动化执行：Playwright Test。

## 快速开始

推荐使用根目录脚本一键启动或关闭前后端。`start` 会先关闭当前脚本记录的进程、同名 macOS `launchctl` 作业，并清理 `8000`、`5173` 端口上的旧监听，再重新启动，避免重复启动或 Vite 自动切到其他端口。

```bash
./dev.sh          # 等同 ./dev.sh start
./dev.sh stop     # 关闭前端和后端
./dev.sh status   # 查看运行状态
./dev.sh logs     # 查看日志路径
```

脚本默认启动：

- 后端：http://127.0.0.1:8000
- 前端：http://127.0.0.1:5173

开发模式下前端会把 `/api` 自动代理到后端，因此使用 Vite 输出的本地或网络地址打开页面都可以连接后端。

在 macOS 上，脚本会用 `beautiful-e2e-backend` 和 `beautiful-e2e-frontend` 两个 `launchctl` 作业托管开发服务；`./dev.sh stop` 会同时卸载这两个作业。

也可以手动启动：

```bash
cp .env.example .env
docker compose up -d mysql

cd backend
uv sync --extra dev
uv run uvicorn app.main:app --reload --port 8000
```

另开一个终端：

```bash
cd frontend
npm install
npm run dev
```

Playwright runner：

```bash
cd runner
npm install
npx playwright install chromium
npm test
```

前后端配合模式下，工作台“运行流程”会使用当前前端环境的 `base_url`
直接执行打开页面、填写、点击和断言步骤，并通过 SSE 返回每一步截图。
纯后端接口模式下，工作台“运行接口”会使用当前接口环境的 `api_base_url`
和请求头逐步发送真实 HTTP 请求，并通过 SSE 返回每一步请求状态。单个接口
步骤失败后最多尝试 3 次；每次失败响应会作为运行期 agent 的上下文，用于
下一次尝试前补充业务变量或修复请求体数据。

如果只是想先看前端工作台，`frontend` 在后端不可用时会展示本地示例数据。

## 可插拔 AI 供应商

后端的 AI 入口现在是可插拔供应商：

- `codex_exec`：默认供应商，直接调用本机 `codex exec`，复用 Codex CLI 当前账号、模型和配置。
- `rule_based`：本地确定性生成器，不依赖外部模型。
- `codex_bridge`：项目内置的 GPT/OpenAI 兼容 HTTP 桥接，可复用 Codex 本地配置。
- `openai_compatible`：自定义 OpenAI 兼容 HTTP 供应商，用于接入互联网通用的 `responses` 或 `chat/completions` 协议。
- 自定义供应商：通过 `AI_PROVIDER_ENTRYPOINT=package.module:factory` 注入，工厂函数接收 `Settings` 并返回带 `name` 和 `generate(context)` 的对象。

`codex_exec` 的常用配置：

1. `AI_PROVIDER=codex_exec`。
2. 可选：`CODEX_EXEC_COMMAND` / `CODEX_EXEC_MODEL` / `CODEX_EXEC_PROFILE` / `CODEX_EXEC_PROFILE_V2` / `CODEX_EXEC_CWD`。
3. 未显式指定模型时，后端让 Codex CLI 读取本机 Codex 配置。
4. 默认不强制 `--sandbox` 或 `--ephemeral`，让 `codex exec` 跟随本机 Codex 配置；需要覆盖时可在 AI 配置弹窗或环境变量中显式设置。
5. 流式生成时后端会调用 `codex exec --json`，把 CLI 显式输出的 reasoning/content JSONL 事件转换为 `provider_delta`。如果当前 CLI 只返回 `turn.completed.usage.reasoning_output_tokens` 这类计数而不返回推理文本，界面不会伪造推理内容。

`codex_exec` 也支持更完整的 Codex CLI 能力配置：`CODEX_EXEC_SANDBOX`、`CODEX_EXEC_EPHEMERAL`、`CODEX_EXEC_SKIP_GIT_REPO_CHECK`、`CODEX_EXEC_IGNORE_USER_CONFIG`、`CODEX_EXEC_IGNORE_RULES`、`CODEX_EXEC_STRICT_CONFIG`、`CODEX_EXEC_OUTPUT_SCHEMA_ENABLED`、`CODEX_EXEC_OSS`、`CODEX_EXEC_LOCAL_PROVIDER`、`CODEX_EXEC_IMAGE_PATHS`、`CODEX_EXEC_ADD_DIRS`、`CODEX_EXEC_CONFIG_OVERRIDES`、`CODEX_EXEC_ENABLED_FEATURES`、`CODEX_EXEC_DISABLED_FEATURES`。布尔值和列表也可以通过工作台“AI 配置”弹窗保存到数据库。

`codex_bridge` 的配置优先级：

1. 项目显式配置：`AI_API_KEY` / `AI_BASE_URL` / `AI_PROVIDER_CONFIG`。
2. 环境变量：`OPENAI_API_KEY` / `OPENAI_BASE_URL`。
3. Codex 本地配置：`CODEX_HOME` 或 `~/.codex/auth.json`、`~/.codex/config.toml`。

使用 `codex_exec`、`codex_bridge` 或 `openai_compatible` 且供应商/CLI 支持流式事件时，
`POST /api/projects/{project_id}/cases/generate/stream` 会额外返回 `provider_delta` 事件。
该事件只转发供应商或 Codex CLI 显式返回的 `reasoning_content`、reasoning summary 或输出文本增量，
前端生成过程弹窗会按“供应商思考”和“供应商输出”合并展示。
`codex_bridge` 和 `openai_compatible` 会在发送前按 HTTP 模型上下文窗口预压缩仓库索引、
引用文档和画布 DSL；如果供应商仍返回上下文超限，后端会用更严格预算自动重试一次，
仍失败时才进入规则生成器兜底。

生成成功时，用例会在 `code_context.generation_mode` 记录实际供应商，例如 `codex_bridge`。

生成提示词可以直接引用本机文档或目录，例如：

```text
根据/absolute/path/to/docs/change-request 生成客户端全流程测试用例
```

后端会读取提示词中存在的本地 Markdown/文本路径，把执行单、需求、页面、用户故事、接口目录、验证等参考资料作为 `reference_documents` 注入 AI 供应商。模型应从文档内容归纳流程，而不是把路径字符串当成测试目标；在 `backend_api` 模式下，“客户端全流程”会被理解为客户端消费的真实接口链路，生成 `api_request` 节点并用当前项目扫描到的控制器路由或 Swagger/OpenAPI 路由补充 `route_source`。如果提示词明确写了“从 X 开始”“不要直接测 Y，要从 X 开始”等入口约束，生成载荷会把 X 提取为 `flow_entrypoint`，要求第一个可执行接口先落到该入口对应的真实列表、分页、搜索、详情、首页或预检路由，不能跳到后续页面或目标接口。每个接口步骤都必须包含非空 `target_url` 和 `data.method`；链路表和测试数据说明只能写入 `step.data`，不会作为缺 URL 的伪接口步骤保存。认证、登录态、Cookie、session、token 和网关请求头统一由项目请求头在运行时注入，即使提示词或文档写了“登录后”，生成 DSL 也不会插入登录接口、token 提取或认证 header 占位符。如果 Swagger/OpenAPI 提供了 `parameters`、`requestBody` 或 `responses`，这些契约会进入 `backend_repository_summary.routes`，用于推导请求参数、请求体和响应提取点。对于需要从上游接口传递的业务实体 ID、状态型业务 ID、业务编号等参数，生成结果应先查找能生产这些参数的上游接口，在生产方步骤写 `data.extract`，在消费方 URL、非认证 headers 或 body 使用 `{{变量}}`，并通过 `data.depends_on` / `data.parameter_links` 记录推测依据；缺少可靠来源时写入 `data.unresolved_parameters` 和 `data.missing_upstream_steps`，便于后续根据运行错误继续反馈。生成结果会在步骤 `data` 或 `code_context.reference_documents` 中保留引用来源，便于后续反馈和修正。

当运行结果出现 404、未知处理器、Method Not Allowed、0 个正确接口或变量无法推导时，后端会把这些现象归纳为通用事实反馈：失败 URL 是反例，下一轮必须重新查项目分析出的真实接口；`{{变量}}` 无生产者则必须先补上游查询、列表、详情、首页、预检或创建接口。反馈保存在 `code_context.api_generation_feedback`，可直接作为后续 prompt/agent 的输入。

可用这个接口检查当前后端 AI 供应商：

```bash
curl http://127.0.0.1:8000/api/ai/provider
```

工作台项目面板里的“AI 配置”按钮会列出 `codex_exec`、GPT HTTP 桥接、OpenAI 兼容自定义供应商和本地规则生成器，并把选择写入数据库的 `ai_provider_configs`。配置里可以分别规划“项目分析”“Prompt 生成 DSL”“接口运行辅助测试”使用哪个 AI，同一个供应商可以承担多个用途；未保存规划时会沿用当前默认供应商。切换主供应商时，原本跟随旧主供应商的用途会同步迁移到新供应商，已手动分配给其他供应商的用途保持不变。

## 本机 MySQL

本地 `.env` 已配置为连接本机 MySQL 的 `beautiful_e2e` 数据库。数据库初始化由 FastAPI 启动时自动执行：

```bash
MYSQL_PWD='******' mysql -uroot -e "CREATE DATABASE IF NOT EXISTS beautiful_e2e CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
cd backend
uv sync --extra dev
uv run uvicorn app.main:app --reload --port 8000
```

后端测试会基于 `DATABASE_URL` 自动创建并重建 `<数据库名>_test` 测试库，避免污染本地开发数据。

## 目录结构

```text
backend/   FastAPI API、数据库模型、仓库扫描、用例生成、Playwright 脚本生成
frontend/  React 工作台、分组列表、自然语言输入、可控制节点图和 DSL 侧栏
runner/    Playwright 执行工程，生成的脚本会落到 tests/generated
docs/      架构、协作流程、API 说明
```

## 推荐迭代路线

1. 接入更多 AI 供应商：在 `backend/app/services/ai/` 下实现 `CaseGenerationProvider`，或通过 `AI_PROVIDER_ENTRYPOINT` 接入团队模型网关。
2. 接入代码索引：把当前轻量扫描升级为 AST、路由表和 API 结构索引，继续增强 Apifox、GraphQL schema 等接口来源。
3. 加执行调度：让测试运行进入队列，按分组或 PR 触发，产出跟踪、视频和 HTML 报告。
4. 加权限模型：团队、项目、角色、审批流、用例变更差异。
5. 加质量门禁：核心链路失败阻断发布，浏览组失败发提醒，低优先级组只记录趋势。
