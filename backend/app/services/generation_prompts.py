from __future__ import annotations

BACKEND_API_ROUTE_GROUNDING_PROMPT = """
后端接口生成必须受真实路由约束。

规则：
1. 把 backend_repository_summary.routes 作为 HTTP 方法、URL 路径、处理函数、
   来源文件和 Swagger/OpenAPI 契约的真实依据。不要根据某个业务域的常见惯例编造端点。
2. 每个 api_request 步骤都必须使用路由目录中的端点；如需路由参数，只能从
   前置响应或显式测试数据中替换出具体 URL。
3. 把路由证据写入 step.data.route_source 和 step.data.route_summary，方便用户
   后续审阅并修正路由选择。
4. 如果用户要求某个业务动作但没有匹配路由，请选择最接近的真实路由，并在
   step.data.route_decision 中说明不确定性；不要输出编造的兜底 URL。
5. 对链式流程，只有在 step.data.extract 或 step.data.depends_on 中说明来源时，
   才能用占位符传递 ID。
6. 除非提示词明确要求管理端或商户行为，客户旅程优先选择客户侧/公开路由。
7. 如果路由来自 Swagger/OpenAPI 或项目分析出的 Java DTO 契约，必须优先参考 route_parameters、route_request_body
   和 route_responses 推导请求参数、请求体和响应提取点；没有明确 example/default 时不要臆造业务 ID。
8. 如果载荷提供 reference_fixtures，先使用其中的 fixed_ids 和 entity_names。文档已经给出
   goodsId、campaignId、displayTitle、campaign_name 或商品/活动名称时，不要退化成地名、范围词或短关键词。
""".strip()


BACKEND_API_ENTRYPOINT_FIRST_PROMPT = """
后端接口生成必须尊重用户指定的流程入口。

规则：
1. 如果用户用“从 X 开始”“先从 X”“入口是 X”“不要直接测 Y，要从 X 开始”等表达指定起点，
   第一个可执行 api_request 必须实现 X 对应的真实接口，而不是 Y 或后续页面/活动接口。
2. 起点 X 要先映射到同领域的 page/list/search/query/detail/home/preview/create 等真实路由；
   如果 X 是列表、分页、搜索或查询意图，优先选择能返回候选业务实体的上游接口。
3. 不允许把“接口链路表”“前置认证”“测试数据说明”“断言策略”等分析性内容伪装成 api_request 步骤；
   这些说明只能写入可执行步骤的 data.flow_reason、data.route_decision 或 data.unresolved_parameters。
4. 每个 api_request 都必须有非空 target_url 和 data.method；缺少真实 URL 时，不要生成该步骤，
   应在最近的可执行步骤 data.missing_upstream_steps 中写明缺口和候选路由。
5. 如果起点接口生产下游需要的业务实体 ID，必须在起点或紧随其后的详情/预检步骤写 data.extract，
   下游 URL、headers 或 body 使用 {{变量名}}，而不是硬编码长 ID。
6. 生成顺序要保持“入口发现接口 -> 详情/确认接口 -> 业务活动/提交接口 -> 结果查询/断言接口”，
   除非用户明确要求从中间状态继续。
""".strip()


API_FLOW_RELATIONSHIP_PROMPT = """
后端接口生成还必须推测接口之间的逻辑关系和参数来源。

规则：
1. 生成步骤前先建立接口链路表，说明每个接口为什么在当前顺序出现，以及它依赖哪些前置状态。
2. 对 path、query、headers、body 中每个业务参数判断来源：固定测试数据、环境配置、前置响应、
   当前步骤输入或无法确定；不要把未知参数填成空字符串来伪装成功链路。
3. 如果参数来自前置响应，必须在生产方 step.data.extract 写入变量名和 JSONPath，例如
   {"业务凭证":"$.data.credential"}；消费方在 target_url、data.headers 或 data.body 中使用
   {{业务凭证}}，并在 step.data.depends_on 或 step.data.parameter_links 说明来源步骤和绑定字段。
4. 凭证、token、code、id、编号、会话和业务实体标识等状态型参数必须优先
   从前置查询、创建、校验、预检或登录接口提取，不能仅凭字段名臆造。
5. 如果缺少可靠来源，保留参数占位并在 step.data.unresolved_parameters 中写出缺口、候选接口和
   需要用户补充的证据，便于下一轮反馈修正。
6. 运行反馈中出现“不能为空”“缺少参数”“未查询到”“无权限”“未命中前置数据”等错误时，
   优先判断为参数链断裂或前置接口未成功，不要继续生成表面连通的错误流程。
7. 后续消费、提交、确认等动作只有在前置步骤成功并抽取到必要变量后才进入；如果前置失败，
   应生成可诊断的断言或缺口说明。
8. 如果某个步骤一开始就需要业务实体 ID（例如 `{entity}Id`、`resourceId`、`recordId`），
   且用户没有明确给出“固定测试夹具 ID”，必须倒推并插入上游查询、
   搜索、列表、详情、首页、预检或创建接口来产生该 ID。不要用长数字、`1`、fallback 或环境变量
   冒充推导结果。
9. 上游发现优先使用真实路由目录里同领域的 page/list/search/options/detail/home/preview/create
   接口：先查询或搜索候选实体，extract 出下游需要的 ID，再把下游路径改成 `{{变量}}`。
10. 如果前一个接口的响应能推导出后一个接口的路径参数，必须从前一个接口 extract。例如首页、详情、
    预检或创建接口返回的实体 ID，要作为后续消费步骤的参数来源。
11. data.parameter_links 里的 fallback 只能作为诊断提示，不能满足 required=true 的依赖；required
    依赖必须有前置 step.data.extract 或用户明确输入的测试夹具。
12. 发现已有画布或运行反馈中某步使用硬编码长 ID、`{{变量}}` 无生产者、或首个关键步骤缺少来源时，
    下一轮生成要先补上生产者步骤，而不是继续让后续接口报“参数不能为空”。
13. 登录态优先遵守 project_context.auth/auth_context：如果项目环境已经配置认证请求头，不要再把同名 header 生成为
    `{{customer_token}}`、`{{access_token}}` 等占位符；只有存在可执行登录接口且 auth_context 未提供
    外部登录态时，才生成登录步骤和 token extract。
""".strip()


API_FACT_FEEDBACK_PROMPT = """
后续反馈修正必须先回到项目事实，而不是围绕失败 DSL 打补丁。

规则：
1. 如果运行反馈出现 404、未知处理器、无法抵达处理器、Method Not Allowed 或接口环境中 0 个正确接口，
   首先判断为路由未命中真实项目接口；下一轮必须重新搜索 backend_repository_summary.routes、
   project_context.repositories[].route_contract_examples 和 reference_documents，不能沿用失败 URL 的路径段。
2. 如果运行反馈出现 “AI 未能推导变量”“运行期 agent 无法从前序响应推导变量” 或
   `{{变量}}` 无法解析，首先判断为缺少上游生产者接口；下一轮必须在消费者之前补充真实的
   page/list/search/query/options/detail/home/preview/create/login/precheck 接口，或把缺口写入
   data.missing_upstream_steps，不能继续让后续接口消费无来源变量。
3. 选择接口时按事实优先级排序：引用文档明确接口地图或固定夹具 > 项目分析路由目录 >
   Swagger/OpenAPI/Java DTO 参数契约 > 运行失败 DSL。失败 DSL 只能作为反例和诊断输入。
4. path、query、headers、body 中的每个参数必须按真实 route_parameters、route_request_body、
   route_responses 或前置 step.data.extract 建立来源。没有来源时写入 unresolved_parameters；
   不要把长数字、`1`、空字符串、地名短词或 fallback 当成标准答案。
5. 反馈摘要应说明“错误接口为什么错、应该查哪个真实路由候选、还缺哪个上游生产者”，
   方便用户把下一轮 prompt 交给任何生成 agent 复用。
""".strip()
