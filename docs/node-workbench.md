# 节点工作台

Beautiful E2E 现在具备可控制的节点工作台：

- 右键节点工具箱：在画布空白处右键呼出节点工具箱，添加页面、点击、输入、断言、接口、子流程、智能体、技能等节点。
- 画布控制：拖拽节点、连接节点、打开选中节点编辑器、删除选中节点。
- 节点编辑弹窗：编辑类型、名称、动作、选择器或 URL、期望结果、接口方法、请求体，并保留扩展元数据。
- DSL 面板：实时 JSON 预览，包含用例元数据、智能体、技能、节点、边和可执行步骤。
- 用例库新建：通过弹窗创建空白用例，调用 `POST /api/projects/{project_id}/cases`；或通过 AI 生成，调用 `POST /api/projects/{project_id}/cases/generate/stream` 并消费 SSE 事件。
- 当前用例重新生成：选中已有用例时，顶部按钮会把 `target_case_id` 传给 `POST /api/projects/{project_id}/cases/generate/stream`，后端替换该用例的步骤和图结构，并默认保留原用例标题、分组、优先级和状态。
- 流式生成：后端按 `start`、`progress`、`provider_delta`、`case`、`done` 或 `error` 事件返回 `text/event-stream`；`codex_exec` 会通过 `codex exec --json` 转发 CLI 暴露的 reasoning/content 增量，HTTP 供应商会转发供应商 SSE 中显式返回的 `reasoning`/`content` 增量，前端生成弹窗会合并展示“供应商思考”和“供应商输出”，并显示本次耗时。收到 `case` 后更新工作台，并在完成后 5 秒自动确认。
- 提示词绑定：选择用例会加载它的 `source_prompt`；保存画布时会把当前提示词持久化回该用例。
- 保存：通过 `PUT /api/cases/{case_id}/graph` 把编辑后的图、可执行步骤和绑定提示词持久化到 MySQL。
- 运行：`fullstack` 模式会调用 `POST /api/cases/{case_id}/run/fullstack/stream`，直接执行打开页面、填写、点击、断言等浏览器动作，并展示每一步截图；`backend_api` 模式会调用 `POST /api/cases/{case_id}/run/backend-api/stream`，按 `start`、`request`、`result`、`done` 或 `error` 事件展示真实 HTTP 请求、状态码、耗时和响应预览。节点编辑弹窗的“单节点调试”会先把调试草稿写入当前节点 DSL 的 `metadata.node_debug_draft` 并通过 `PUT /api/cases/{case_id}/graph` 入库，再向运行接口传入 `step_id` 和当前节点草稿 `step_override`，只执行当前接口节点；调试草稿可覆盖请求方法、Path、Path 参数、Query 参数、Body 和期望状态。单节点调试不会调用运行期 agent，缺少变量时会直接提示用户手动补齐参数。
- 模式切换：`fullstack` 表示浏览器 + 后端上下文，`backend_api` 表示纯接口回归。后端接口模式会发送 `execution_mode=backend_api`，引导生成接口节点；前后端配合模式会保留页面动作节点，让平台直接运行当前 DSL。
- 环境切换：项目面板和项目新建/编辑弹窗按环境保存前端/接口基础地址。前端环境和接口环境可分别从基础地址输入框旁的下拉框选择。接口环境还拥有可搜索的请求头键值行，因此生成的接口请求会复用项目界面中输入的精确值。生成后端接口 DSL 时，认证、登录态、Cookie、session、token 和网关请求头统一视为项目请求头能力，后端只把请求头名称传给模型，不传真实值，也不会把登录接口、token 提取或 `{{customer_token}}` 这类认证 header 占位符写进 DSL。运行时仍可通过 `BASE_URL`、`API_BASE_URL`、`E2E_ENV` 和 `REQUEST_HEADERS_JSON` 覆盖。
- 项目分析：创建项目时可立即分析，项目面板也提供更新分析操作。重新分析调用 `POST /api/projects/{project_id}/analyze/stream`，按 `start`、`progress`、`project`、`done` 或 `error` 事件展示仓库扫描、认证画像和索引写入进度，并复用流式弹窗显示耗时。分析结果会把后端路由、前端 DOM 目标和认证画像存入 `repositories.index_summary`；后续生成会先复用该持久化索引，再扫描实时文件。认证画像会初判登录方式是环境请求头、可执行登录接口、小程序/第三方外部登录，还是未知。项目分析中心的“接口”页签支持按方法、路径、摘要、参数、请求体字段和来源文件搜索，便于把运行失败反馈回真实路由契约。
- 项目级 LLM 上下文：后端会通过统一的 `project_llm_context` 把当前环境、脱敏后的认证画像、仓库分析摘要和共享规则传给生成 DSL LLM 与接口运行辅助 LLM。生成 DSL 前会剥离登录候选接口，只保留项目请求头 key 和业务变量规则，避免不同模型把登录态建模成 DSL 步骤。

生成请求可以包含智能体和技能选择：

```json
{
  "target_case_id": "已有用例 id，重新生成时传入；新建生成时省略",
  "execution_mode": "backend_api",
  "agent_id": "...",
  "skill_ids": ["..."],
  "canvas_dsl": {
    "nodes": [],
    "edges": [],
    "steps": []
  }
}
```

未显式选择档案时，纯后端接口模式会注入内置接口逻辑与参数推测智能体，
并同时启用入口优先、路由约束、参数来源推测技能。
Codex 桥接生成器会把这些字段放进发送给已配置 Codex 供应商的提示词中，
生成的用例会把注入的智能体/技能提示词保存在 `code_context`，便于后续审阅和反馈。

如果提示词明确写出“从 X 开始”“先从 X”“不要直接测 Y，要从 X 开始”等入口约束，
后端会把入口抽取为 `flow_entrypoint` 传给 DSL 生成 LLM。纯接口模式下第一个
可执行 `api_request` 必须先匹配这个入口对应的真实路由，分析性链路表、认证说明
或测试数据说明只能写入 `step.data.flow_reason`、`route_decision` 或缺口诊断字段，
不能保存成缺少 URL 的接口节点。
如果提示词同时表达“真实找到”“查出来”“从分页/列表/搜索/查询开始再用 ID”等动态发现意图，
`flow_entrypoint.requires_dynamic_discovery` 会置为 `true`。此时引用文档里的固定 ID 只能作为
搜索过滤、候选校验或断言依据，不能直接满足下游 path/query/body 的必填业务 ID。生成结果在
保存前还会写入 `code_context.api_entrypoint_flow_enforcement`，记录是否插入或重排了入口接口、
是否把硬编码 ID 改成了前置 `step.data.extract` 变量。

接口请求节点保存时会把请求体编辑器映射到 `step.data.body`。额外的后端路由证据
或前端专属字段会保存在 `node.data.metadata`，并通过 `step.data` 往返传递，
让生成用例保留供应商特定上下文，同时不挤占主编辑字段。

接口链式参数使用统一契约：前置步骤通过 `step.data.extract` 声明响应 JSONPath，
后续步骤可在 `target_url`、非认证 `step.data.headers` 或 `step.data.body` 中写 `{{变量}}`。
认证、登录态、Cookie、session、token 和网关请求头由项目请求头注入，不通过 DSL 变量链维护。
如果消费步骤需要业务 ID 但没有生产者，生成器应先补上游搜索、列表、详情、首页、
预检或创建接口；后端也会把硬编码长 ID、无生产者占位等问题诊断到
`step.data.missing_upstream_steps`。平台运行接口和导出的 Playwright spec 都会真实解析这些变量；
如果生成器无法确定来源，应把缺口写入 `step.data.unresolved_parameters`，
让运行错误能反馈回下一轮生成。

接口运行时还有一层受限推导：当 `{{变量}}` 未解析且已有前序响应时，运行器先按变量名别名
从前序 JSON 响应里确定性查找；仍找不到且启用 `API_RUNTIME_AI_INFERENCE_ENABLED` 时，才把
前序响应预览和当前步骤契约交给 AI agent 抽取。这个 agent 只能从已执行响应中取值，
不能为首个业务 ID 编造测试数据，因此缺上游步骤的问题仍会反馈回生成阶段。
如果未解析变量只出现在请求头里，并且项目环境已经配置了同名且非空的请求头，运行器会使用
环境值并跳过该 DSL header 占位符；这个兼容层只适用于请求头登录态，不会跳过 URL 或 Body
里的业务变量。

生成后反馈会写入 `code_context.api_generation_feedback`。它把 404、未知处理器、错误 method/path、
无来源 `{{变量}}`、硬编码长 ID 和缺少上游生产者等现象整理成下一轮 agent 可读的事实提示。
如果入口顺序或动态发现参数被后处理修正，反馈里还会包含 `entrypoint_flow_enforcement`，用于提示
下一轮 agent 先修入口发现链路，再修下游接口参数。
后续 prompt 应把这些失败 URL 当作反例，重新从项目分析中心和 `backend_repository_summary.routes`
里的真实 path、query、body 契约选接口。
