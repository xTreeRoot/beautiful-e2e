# Beautiful E2E 编码规范

本文件适用于仓库根目录及其全部子目录。后续任何智能体或开发者改代码前，必须先阅读并遵守这里的规则。

## 项目画像

Beautiful E2E 是一个端到端自动化测试平台雏形：

- `backend/`：FastAPI、SQLAlchemy、Pydantic，负责项目/用例/分组/API、仓库扫描、AI 用例生成、Playwright spec 导出。
- `frontend/`：React、TypeScript、Vite、Ant Design、React Flow，负责工作台、节点图、用例编辑和导出入口。
- `runner/`：Playwright Test 工程，承载生成后的 E2E spec。
- `docs/`：架构、协作流程、本地 bridge/MySQL 等说明。

当前代码中 `backend/app/api/routes.py` 和 `frontend/src/App.tsx` 文件偏大。`backend/app/services/ai_case_generator.py` 曾经同时承担规则编排、文档解析、接口文档提取、后端路由匹配和图结构输出，已经拆为明确边界的服务模块。后续新增能力时，优先拆分到服务、结构定义、钩子、组件、工具文件中，不继续把复杂逻辑堆进单个文件。

本项目使用 GitHub 账号 `xTreeRoot` 作为仓库提交归属。重建历史、创建提交或修正提交者信息时，必须保持本仓库 Git 配置与提交 author/committer 一致，统一使用 `xTreeRoot <79004055+xTreeRoot@users.noreply.github.com>`，确保提交归入 https://github.com/xTreeRoot。

## 通用编码原则

- 保持改动聚焦：一次变更只解决一个明确问题，不夹带无关重构。
- 先读现有代码再写代码：沿用当前技术栈、命名、错误处理和返回结构。
- 修改 `.ts`、`.tsx`、`.py` 文件时，如果发现当前文件职责过大、边界过泛，必须先梳理职责并拆到新的组件、hook、service、schema、lib 或 utils 文件；新增功能或修复问题时，不得继续把逻辑堆进原文件。
- 业务逻辑要可读、可测、可回滚：避免隐藏副作用，避免魔法字符串散落在多处。
- 不提交本地密钥、真实密码、token、绝对个人路径；示例配置放 `.env.example`。
- 用户可见文案、代码注释、文档中的领域术语必须使用中文；变量、函数、类型、文件名统一使用英文。
- 框架、库、协议、命令、文件路径、API 字段等固定英文名称保留原文；业务概念首次出现时优先写中文，必要时补充英文原词，例如“用例（case）”。
- 新增或调整 API、数据结构、执行命令时，同步更新 `README.md` 或 `docs/` 中对应说明。

## 注释规范

代码必须有必要注释，但不要写无效注释。注释必须全部使用中文，解释“为什么这样做”和“边界是什么”，不重复代码已经表达清楚的“做了什么”。

必须写注释的场景：

- 非直观业务规则，例如用例分组策略、AI 生成兜底策略、节点到 Playwright 动作的映射规则。
- 有兼容性、降级、重试、幂等、事务、权限、安全风险的逻辑。
- 跨层契约，例如前端图结构/步骤 DSL 与后端结构定义、Playwright 生成器的字段约定。
- 临时方案、技术债、待替换实现，必须写清原因和后续处理方向。
- 公共函数、复杂 helper、service 类，必须用中文 docstring 或 JSDoc 说明输入、输出和关键约束。

禁止的注释：

- `# 设置名称`、`// 调用接口` 这类重复代码的注释。
- 只有 `TODO` 没有上下文的注释。TODO 必须说明原因、目标和触发条件。
- 为了“看起来有注释”而给每行代码配旁白。

推荐格式：

```python
def build_case_graph(steps: list[TestStep]) -> dict:
    """把持久化步骤转换为 React Flow 消费的图结构契约。

    节点 id 必须保持稳定，因为前端会按 id 保存选中节点状态。
    """
```

```ts
/**
 * 把后端图结构载荷转换为 React Flow 节点。
 * 未知字段需要保留，因为生成的 Playwright 步骤可能携带供应商特定元数据。
 */
function toCanvasNodes(caseItem: TestCase): CanvasNode[] {
  // ...
}
```

## 后端规范

- Python 版本按 `backend/pyproject.toml`：`>=3.11`。
- 使用类型标注；新增函数必须标注参数和返回值。
- API 层只做请求校验、权限/存在性检查、事务编排和响应组装；复杂业务放到 `backend/app/services/`。
- Pydantic schema 放在 `backend/app/schemas.py` 或按领域拆到 `backend/app/schemas/`；SQLAlchemy ORM 只放持久化字段和关系。
- 数据库写操作要明确事务边界：同一个业务动作只在一个地方 `commit()`，异常路径要保证不会留下半写状态。
- 查询默认使用 SQLAlchemy `select()` 风格，并用 `selectinload` 解决明确的 N+1 风险。
- 对外错误使用 `HTTPException`，错误信息要能指导前端或调用者定位问题。
- 新增服务类时，优先让构造函数只接收配置或依赖，不直接读取全局状态，便于测试。
- Ruff 行宽为 100；提交前运行 `cd backend && uv run ruff check .`。

## 前端规范

- TypeScript 必须显式建模 API 数据；只在外部 JSON、透传 metadata、动态 graph payload 使用 `unknown`。
- React 组件保持职责单一。新增工作台功能时优先拆分：
  - `src/components/`：可复用 UI 组件。
  - `src/hooks/`：状态同步、请求、画布交互等 hooks。
  - `src/lib/` 或 `src/utils/`：纯函数、转换器、常量。
  - `src/types/`：共享类型。
- 避免继续扩大 `src/App.tsx`；新增超过 80 行的独立 UI 或逻辑，应拆文件。
- API 调用统一经过 `src/api.ts`，不要在组件里散写 `fetch()`。
- 事件处理函数命名使用 `handleXxx`，派生数据使用 `useMemo`，稳定回调用 `useCallback`。
- UI 使用 Ant Design 和 lucide-react 的既有风格；新增按钮类操作应优先配图标和 tooltip。
- 所有新建、编辑类操作优先使用弹窗或抽屉承载表单，不把输入项挤在侧栏、列表或工具栏里。
- 用户可见状态要覆盖 loading、empty、error、offline/demo 四类场景。
- 提交前运行 `cd frontend && npm run build`。

## Playwright 规范

- 测试文件命名使用 `*.spec.ts`，用例标题描述真实业务行为，不写泛泛的 “test works”。
- 优先使用 role/text/label/test id 等稳定 locator，少用脆弱 CSS 层级选择器。
- 每个测试要有清晰的“准备 / 操作 / 断言”结构；复杂流程用中文注释标出阶段。
- 生成到 `runner/tests/generated/` 的代码要保持可读，不把大段不可维护 DSL 塞进单行字符串。
- 提交前运行 `cd runner && npm test`；只改生成器时至少补充或检查一个生成 spec 样例。

## 文件拆分建议

后端：

- `backend/app/api/routes.py` 超过 800 行时，不再直接追加大型业务路由。
- 新增项目、分组、用例、导出相关路由时，优先拆成 `backend/app/api/projects.py`、`groups.py`、`cases.py`、`exports.py` 等模块。
- 生成、导出、仓库扫描、bridge 调用都应留在 `services/`，API 层只调用服务。
- `backend/app/services/ai_case_generator.py` 只作为规则兜底生成器门面，负责选择生成路径、组装 `GeneratedCase` 和兼容旧调用；不得再加入新的文档正则、路由评分、接口链路推断或图布局细节。
- 用例生成相关职责按模块落位：生成结果类型放 `backend/app/services/case_generation_types.py`；React Flow 图结构放 `backend/app/services/case_graph_builder.py`；引用产品文档到浏览器步骤的兜底逻辑放 `backend/app/services/document_case_steps.py`；真实接口文档解析、参数链路和后端路由匹配放 `backend/app/services/api_case_steps.py`。
- `backend/app/api/cases.py` 曾超过 1000 行，目前仍接近 900 行；生成目标校验、分组归属、保存生成结果和仓库摘要选择已拆到 `backend/app/api/case_generation_helpers.py`。后续触碰生成流、运行流或保存生成结果时，优先继续拆到独立 API helper 或服务层；API 文件只保留路由声明、请求校验和响应组装。

前端：

- `frontend/src/App.tsx` 已超过 2000 行，后续改动必须优先抽离组件或 hooks。
- `frontend/src/api.ts` 同时包含类型、基础请求、SSE 解析和 demo 数据，后续触碰任一职责时应按 `src/types/api.ts`、`src/api/client.ts`、`src/api/streams.ts`、`src/demoData.ts` 方向小步拆分，保持 `src/api.ts` 只做兼容导出。
- `frontend/src/hooks/useWorkbenchController.ts` 是工作台入口控制器，只保留项目、用例、画布和异步动作的顶层编排；不要继续把独立 UI 状态机塞回这个文件。它之前同时承担工作区初始化、项目/分组/用例 CRUD、AI 生成流式进度、运行进度、画布同步等职责，导致边界不清、变更风险集中。
- AI 生成过程已拆到 `frontend/src/hooks/useGenerateProgress.ts`，负责生成弹窗、供应商 SSE reasoning/content 增量合并、生成完成/错误状态；用例运行过程已拆到 `frontend/src/hooks/useCaseRunProgress.ts`，负责浏览器/接口运行 SSE、步骤状态合并、运行期变量推导展示状态；画布交互已拆到 `frontend/src/hooks/useWorkbenchCanvas.ts`，负责 React Flow 节点/边、选中节点、右键工具箱和画布编辑动作；分组/用例集合已拆到 `frontend/src/hooks/useWorkbenchCollections.ts`；项目设置、环境和项目表单已拆到 `frontend/src/hooks/useWorkbenchProjectSettings.ts`；项目异步动作已拆到 `frontend/src/hooks/useWorkbenchProjectActions.ts`；当前用例生成、保存、运行已拆到 `frontend/src/hooks/useWorkbenchCaseActions.ts`。后续新增类似流程时，优先新建领域 hook，让 `useWorkbenchController` 只调用“开始、追加事件、完成/失败、应用到画布、保存项目设置”这类语义接口。
- 画布节点转换、DSL 构建、项目设置解析等纯逻辑，应移到独立工具文件并补充必要注释。
- 表单弹窗、侧栏列表、工具箱、节点属性面板应拆成组件，避免一个组件同时管理全局状态和细节 UI。

## 职责边界巡检与防膨胀规则

为什么要这么做：

- 单文件把生成编排、解析、匹配、持久化或 UI 细节混在一起时，任何小改动都会扩大回归面，测试也很难只覆盖一个业务边界。
- 规则兜底生成器需要长期演进，如果继续把接口文档正则、路由评分、浏览器步骤模板和图布局堆在一个文件里，后续接入供应商或新增 DSL 字段会越来越难回滚。
- 大文件会诱导智能体和开发者“就近追加”，让架构继续恶化；拆出明确模块后，新增逻辑有固定落点。

如何做：

- 修改前先用 `find backend/app frontend/src -type f \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' \) -print | xargs wc -l | sort -nr | head` 找出大文件，再用 `rg -n "class |def |async def |export |function"` 看职责是否混杂。
- 先按稳定契约拆类型和纯函数，再拆业务策略，最后保留一个薄门面兼容旧导入；不要在一次变更里同时重命名大量调用点。
- 拆分后必须让旧测试仍从原入口验证行为，例如 `CaseGenerator().generate(...)` 仍然是规则兜底生成入口。

后续怎么做：

- 新增浏览器步骤兜底策略时，优先改 `document_case_steps.py` 或新建同级策略模块。
- 新增真实接口链路、参数推断、路由评分或接口文档解析时，优先改 `api_case_steps.py`；如果该文件继续超过 900 行，按“接口文档解析”“路由匹配评分”“参数依赖诊断”继续拆。
- 新增图布局或前端画布契约时，优先改 `case_graph_builder.py`，并同步说明前后端 DSL 字段约束。
- 触碰 `cases.py`、`api.ts`、`useWorkbenchController.ts` 这类已标记文件时，先抽离独立职责，再实现新需求。

怎样防止：

- `.py`、`.ts`、`.tsx` 单文件超过 600 行时，新增功能前必须在本文件或 AGENTS.md 说明为什么暂不拆；超过 900 行时，除紧急修复外必须先拆分。
- 新增函数如果同时需要读取 prompt、解析文档、匹配路由、写数据库或更新 UI 状态中的两类以上职责，应拆到 service、hook、lib 或 schema 层。
- 评审时优先检查“新增逻辑是否放在正确模块”，而不是只看代码能否运行；发现门面文件新增复杂私有方法，应要求迁移到领域模块。

## 推送前安全扫描

任何推送到公开仓库前，必须先确认 Git 会发布的内容是干净的。扫描时只报告命中位置和类型，不在终端、回复或日志中复述完整密钥值。

必须检查：

- 当前快照不能包含真实密钥、token、密码、私钥、Cookie、个人姓名、个人邮箱、本机用户名、本机绝对路径或 IDE/虚拟环境/构建产物。
- Git 作者和提交者必须是本仓库约定身份 `xTreeRoot <79004055+xTreeRoot@users.noreply.github.com>`。
- remote URL 不能包含 token、用户名密码或其他凭证。
- 如果公开仓库要保留历史，必须扫描全部历史提交；如果历史里出现个人路径或敏感内容，不能直接推送旧历史，应改用干净的 orphan 首提交发布。
- `.env`、`.idea/`、`.venv/`、`node_modules/`、`dist/`、`build/`、`.DS_Store` 和生成的本地 spec 只能作为被忽略的本地文件存在，不能进入待提交列表。

推荐命令：

```bash
git status --short --ignored
git remote -v
git log --format='%H %P %an <%ae> %cn <%ce> %s'
git ls-files --cached --others --exclude-standard | rg -n -i '(^|/)(\.env$|\.env\.|\.DS_Store$|\.idea/|\.venv/|node_modules/|dist/|build/|.*\.pem$|.*\.key$|id_rsa$|id_ed25519$|.*credential.*|.*secret.*)'
git ls-files --cached --others --exclude-standard -z | xargs -0 rg -n -I -e '<本机用户名>|<个人邮箱关键词>|<个人姓名>|<本机绝对路径前缀>'
git ls-files --cached --others --exclude-standard -z | xargs -0 rg -n -I -e '(sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN (RSA|DSA|EC|OPENSSH|PRIVATE) KEY-----|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})'
```

保留历史推送时，还必须额外扫描历史：

```bash
for rev in $(git rev-list --all); do
  git grep -n -I -e '<本机用户名>' -e '<个人邮箱关键词>' -e '<个人姓名>' -e '<本机绝对路径前缀>' "$rev" -- ':!*.png' ':!*.jpg' ':!*.jpeg' ':!*lock' || true
  git grep -n -I -E '(sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN (RSA|DSA|EC|OPENSSH|PRIVATE) KEY-----|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})' "$rev" -- ':!*.png' ':!*.jpg' ':!*.jpeg' ':!*lock' || true
done
```

发现疑似敏感信息时，必须停止推送并先清理：当前快照命中就改文件或 `.gitignore`；历史命中就重写历史或创建干净 orphan 首提交；真实密钥一旦进入历史，应视为泄露并轮换。

## 验证清单

根据改动范围选择最小但有效的验证：

- 后端：`cd backend && uv run ruff check .`
- 后端测试：`cd backend && uv run pytest`
- 前端：`cd frontend && npm run build`
- Playwright 执行工程：`cd runner && npm test`
- 全链路改动：启动 backend/frontend 后，再跑 runner smoke。

如果因为环境缺失无法运行验证，必须在最终说明中写清楚未运行的命令和原因。

## 智能体工作要求

- 开始修改前先扫描相关文件，确认是否已有模式可复用。
- 修改前向用户说明将改哪些文件和原因。
- 不覆盖用户已有改动；发现无关未跟踪或未提交文件时保持原样。
- 代码完成后报告实际改动、验证结果、遗留风险。
- 发现架构继续恶化时，优先小步拆分，不做一次性大重构。
