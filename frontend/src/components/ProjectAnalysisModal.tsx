import { Button, Empty, Flex, Input, Modal, Space, Tag, Typography } from 'antd';
import { BarChart3, Braces, FileCode2, GitBranch, Network, RefreshCw, Route, Search } from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';
import type { Project, Repository } from '../api';
import { useProjectKnowledgeGraph } from '../hooks/useProjectKnowledgeGraph';
import { ProjectKnowledgeGraphPanel } from './ProjectKnowledgeGraphPanel';

const { Text, Title } = Typography;

type DetailView = 'overview' | 'graph' | 'routes' | 'dom' | 'raw';
type ToastType = 'success' | 'info' | 'warning' | 'error';

type ProjectAnalysisModalProps = {
  open: boolean;
  project?: Project;
  loading: boolean;
  onClose: () => void;
  onRunAnalysis: () => void;
  showToast?: (type: ToastType, content: string) => void;
};

type IndexSummary = {
  analysis?: Record<string, unknown>;
  routes?: Array<Record<string, unknown>>;
  dom_targets?: Array<Record<string, unknown>>;
  signals?: string[];
  files?: string[];
  exists?: boolean;
};

type RouteParameter = {
  name?: unknown;
  in?: unknown;
  required?: unknown;
  description?: unknown;
  schema?: { type?: unknown };
};

const ANALYSIS_VIEW_OPTIONS: Array<{
  value: DetailView;
  label: string;
  description: string;
  icon: ReactNode;
}> = [
  { value: 'overview', label: '概览', description: '项目分析摘要', icon: <BarChart3 size={16} /> },
  { value: 'graph', label: '图谱', description: '模块、入口和链路关系', icon: <GitBranch size={16} /> },
  { value: 'routes', label: '接口', description: '路由、参数和请求体', icon: <Route size={16} /> },
  { value: 'dom', label: 'DOM', description: '页面目标和选择器', icon: <FileCode2 size={16} /> },
  { value: 'raw', label: '原始', description: '完整分析 JSON', icon: <Braces size={16} /> }
];

export function ProjectAnalysisModal({
  open,
  project,
  loading,
  onClose,
  onRunAnalysis,
  showToast
}: ProjectAnalysisModalProps) {
  const repositories = project?.repositories ?? [];
  const [detailView, setDetailView] = useState<DetailView>('overview');
  const [routeSearch, setRouteSearch] = useState('');
  const {
    knowledgeGraph,
    isLoadingKnowledgeGraph,
    isSavingKnowledgeGraph,
    knowledgeGraphError,
    loadKnowledgeGraph,
    rebuildKnowledgeGraph,
    saveKnowledgeGraph,
    approveKnowledgeGraph
  } = useProjectKnowledgeGraph({ open, project, showToast });
  const routeTotal = useMemo(
    () => repositories.reduce((total, repo) => total + (indexSummary(repo).routes?.length ?? 0), 0),
    [repositories]
  );
  const domTotal = useMemo(
    () => repositories.reduce((total, repo) => total + (indexSummary(repo).dom_targets?.length ?? 0), 0),
    [repositories]
  );
  const graphModuleTotal = knowledgeGraph?.graph.modules?.length ?? 0;
  const currentView = ANALYSIS_VIEW_OPTIONS.find((option) => option.value === detailView)
    ?? ANALYSIS_VIEW_OPTIONS[0];

  const handleSelectView = (view: DetailView) => {
    setDetailView(view);
    if (view !== 'routes') setRouteSearch('');
  };
  const viewCount = (view: DetailView): string => {
    if (view === 'overview') return `${repositories.length} 记录`;
    if (view === 'graph') return `${graphModuleTotal} 模块`;
    if (view === 'routes') return `${routeTotal} 接口`;
    if (view === 'dom') return `${domTotal} DOM`;
    return 'JSON';
  };

  const canRenderDetail = detailView === 'graph' || repositories.length > 0;
  const detailSubtitle = detailView === 'graph'
    ? project?.name ?? '当前项目'
    : `${repositories.length} 条分析记录 · ${routeTotal} 接口 · ${domTotal} DOM`;

  const viewOptions = ANALYSIS_VIEW_OPTIONS.map((option) => (
    <button
      key={option.value}
      type="button"
      className={option.value === detailView ? 'analysis-view-card active' : 'analysis-view-card'}
      onClick={() => handleSelectView(option.value)}
    >
      <span className="analysis-view-icon" aria-hidden="true">{option.icon}</span>
      <span className="analysis-view-copy">
        <Text strong>{option.label}</Text>
        <Text className="analysis-path">{option.description}</Text>
      </span>
      <Tag>{viewCount(option.value)}</Tag>
    </button>
  ));

  return (
    <Modal
      className="analysis-modal-shell"
      rootClassName="analysis-modal-root"
      title={
        <Flex align="center" justify="space-between" gap={16} className="analysis-modal-titlebar">
          <Flex align="center" gap={10} className="analysis-modal-title">
            <Network size={18} aria-hidden="true" />
            <span>项目分析中心</span>
          </Flex>
          <Button
            type="primary"
            className="primary-button"
            icon={<RefreshCw size={16} />}
            loading={loading}
            onClick={onRunAnalysis}
          >
            重新分析
          </Button>
        </Flex>
      }
      open={open}
      onCancel={onClose}
      width="100vw"
      footer={null}
    >
      <div className="analysis-modal-layout">
        <aside className="analysis-records" aria-label="分析视图">
          <Flex align="center" justify="space-between" className="analysis-panel-heading">
            <Text className="field-label">选择视图</Text>
            <Tag>{ANALYSIS_VIEW_OPTIONS.length}</Tag>
          </Flex>
          <div className="analysis-view-list">{viewOptions}</div>
        </aside>

        <section className="analysis-detail" aria-label="分析详情">
          {canRenderDetail ? (
            <>
              <AnalysisDetailContent
                repositories={repositories}
                view={detailView}
                routeSearch={routeSearch}
                onRouteSearchChange={setRouteSearch}
                knowledgeGraph={knowledgeGraph}
                isLoadingKnowledgeGraph={isLoadingKnowledgeGraph}
                isSavingKnowledgeGraph={isSavingKnowledgeGraph}
                knowledgeGraphError={knowledgeGraphError}
                onReloadKnowledgeGraph={() => void loadKnowledgeGraph()}
                onRebuildKnowledgeGraph={() => void rebuildKnowledgeGraph()}
                onSaveKnowledgeGraph={(nextGraph, reviewStatus) => void saveKnowledgeGraph(nextGraph, reviewStatus)}
                onApproveKnowledgeGraph={() => void approveKnowledgeGraph()}
              />
            </>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择一条分析记录查看详情" />
          )}
        </section>
      </div>
    </Modal>
  );
}

function AnalysisDetailContent({
  repositories,
  view,
  routeSearch,
  onRouteSearchChange,
  knowledgeGraph,
  isLoadingKnowledgeGraph,
  isSavingKnowledgeGraph,
  knowledgeGraphError,
  onReloadKnowledgeGraph,
  onRebuildKnowledgeGraph,
  onSaveKnowledgeGraph,
  onApproveKnowledgeGraph
}: {
  repositories: Repository[];
  view: DetailView;
  routeSearch: string;
  onRouteSearchChange: (value: string) => void;
  knowledgeGraph: ReturnType<typeof useProjectKnowledgeGraph>['knowledgeGraph'];
  isLoadingKnowledgeGraph: boolean;
  isSavingKnowledgeGraph: boolean;
  knowledgeGraphError: string | null;
  onReloadKnowledgeGraph: () => void;
  onRebuildKnowledgeGraph: () => void;
  onSaveKnowledgeGraph: (
    nextGraph: NonNullable<ReturnType<typeof useProjectKnowledgeGraph>['knowledgeGraph']>['graph'],
    reviewStatus?: string
  ) => void;
  onApproveKnowledgeGraph: () => void;
}) {
  const summaries = useMemo(() => repositories.map(indexSummary), [repositories]);
  const routes = useMemo(() => summaries.flatMap((summary) => summary.routes ?? []), [summaries]);
  const domTargets = useMemo(() => summaries.flatMap((summary) => summary.dom_targets ?? []), [summaries]);
  const signals = useMemo(
    () => Array.from(new Set(summaries.flatMap((summary) => summary.signals ?? []))),
    [summaries]
  );
  const files = useMemo(
    () => Array.from(new Set(summaries.flatMap((summary) => summary.files ?? []))),
    [summaries]
  );
  const filteredRoutes = useMemo(
    () => filterRoutes(routes, routeSearch),
    [routes, routeSearch]
  );

  if (view === 'graph') {
    return (
      <ProjectKnowledgeGraphPanel
        graph={knowledgeGraph}
        loading={isLoadingKnowledgeGraph}
        saving={isSavingKnowledgeGraph}
        error={knowledgeGraphError}
        onReload={onReloadKnowledgeGraph}
        onRebuild={onRebuildKnowledgeGraph}
        onSaveGraph={onSaveKnowledgeGraph}
        onApprove={onApproveKnowledgeGraph}
      />
    );
  }

  if (!repositories.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无分析记录" />;
  }

  if (view === 'routes') {
    return (
      <div className="analysis-detail-list analysis-routes-list">
        <Input
          className="analysis-route-search"
          allowClear
          prefix={<Search size={15} aria-hidden="true" />}
          placeholder="搜索接口路径、方法、摘要、参数、请求体或来源"
          value={routeSearch}
          onChange={(event) => onRouteSearchChange(event.target.value)}
        />
        <div className="analysis-route-results">
          {routes.length ? (
            <>
              <Flex align="center" justify="space-between" className="analysis-list-toolbar">
                <Text className="field-label">接口结果</Text>
                <Tag>{filteredRoutes.length} / {routes.length}</Tag>
              </Flex>
              {filteredRoutes.length ? filteredRoutes.slice(0, 120).map((route, index) => (
                <DetailRow
                  key={`${String(route.path)}-${index}`}
                  icon={<Network size={15} />}
                  title={`${String(route.method ?? 'GET')} ${String(route.path ?? '/')}`}
                  meta={String(route.summary ?? route.handler ?? '')}
                  source={String(route.source ?? '')}
                  details={<RouteContractSummary route={route} />}
                />
              )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的接口" />}
            </>
          ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无接口路由" />}
        </div>
      </div>
    );
  }

  if (view === 'dom') {
    return (
      <div className="analysis-detail-list">
        {domTargets.length ? domTargets.slice(0, 80).map((target, index) => (
          <DetailRow
            key={`${String(target.value)}-${index}`}
            icon={<FileCode2 size={15} />}
            title={`${String(target.kind ?? 'target')}: ${String(target.value ?? '')}`}
            meta={String(target.hint ?? '')}
            source={String(target.source ?? '')}
          />
        )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 DOM 目标" />}
      </div>
    );
  }

  if (view === 'raw') {
    return (
      <pre className="analysis-raw-json">
        {JSON.stringify(repositories.map((repo) => ({
          kind: repo.kind,
          path: repo.path,
          index_summary: repo.index_summary ?? {}
        })), null, 2)}
      </pre>
    );
  }

  return (
    <div className="analysis-overview-grid">
      <Metric label="接口路由" value={routes.length} />
      <Metric label="DOM 目标" value={domTargets.length} />
      <Metric label="扫描文件" value={files.length} />
      <Metric label="分析状态" value={analysisStatusForSummaries(summaries)} />
      <div className="analysis-overview-wide">
        <Text className="field-label">最近分析</Text>
        <Text>{formatLatestAnalyzedAt(summaries)}</Text>
      </div>
      <div className="analysis-overview-wide">
        <Text className="field-label">关键信号</Text>
        {signals.length ? (
          <div className="analysis-signal-list">
            {signals.slice(0, 8).map((signal) => (
              <Tag key={signal}>{signal.length > 64 ? `${signal.slice(0, 64)}...` : signal}</Tag>
            ))}
          </div>
        ) : (
          <Text className="analysis-path">暂无信号</Text>
        )}
      </div>
    </div>
  );
}

function DetailRow({
  icon,
  title,
  meta,
  source,
  details
}: {
  icon: ReactNode;
  title: string;
  meta: string;
  source: string;
  details?: ReactNode;
}) {
  return (
    <div className="analysis-detail-row">
      <span className="analysis-detail-icon">{icon}</span>
      <div>
        <Text strong>{title}</Text>
        {meta ? <Text className="analysis-path">{meta}</Text> : null}
        {source ? <Text className="analysis-source">{source}</Text> : null}
        {details}
      </div>
    </div>
  );
}

function RouteContractSummary({ route }: { route: Record<string, unknown> }) {
  const parameters = routeParameters(route);
  const bodyFields = routeBodyFields(route);
  if (!parameters.length && !bodyFields.length) {
    return <Text className="analysis-path">暂无参数契约</Text>;
  }
  return (
    <div className="analysis-contract-tags">
      {parameters.map((parameter) => (
        <Tag key={`${String(parameter.in)}-${String(parameter.name)}`}>
          {formatParameterTag(parameter)}
        </Tag>
      ))}
      {bodyFields.map((field) => (
        <Tag key={`body-${field}`}>Body {field}</Tag>
      ))}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="analysis-metric">
      <Text className="field-label">{label}</Text>
      <Text strong>{value}</Text>
    </div>
  );
}

function indexSummary(repository: Repository): IndexSummary {
  return (repository.index_summary ?? {}) as IndexSummary;
}

function filterRoutes(
  routes: Array<Record<string, unknown>>,
  keyword: string
): Array<Record<string, unknown>> {
  const normalized = keyword.trim().toLowerCase();
  if (!normalized) return routes;
  return routes.filter((route) => routeSearchText(route).includes(normalized));
}

function routeSearchText(route: Record<string, unknown>): string {
  const values = [
    route.method,
    route.path,
    route.summary,
    route.description,
    route.handler,
    route.source,
    ...routeParameters(route).flatMap((parameter) => [
      parameter.name,
      parameter.in,
      parameter.description,
      parameter.schema?.type
    ]),
    ...routeBodyFields(route)
  ];
  return values.map((value) => String(value ?? '').toLowerCase()).join(' ');
}

function routeParameters(route: Record<string, unknown>): RouteParameter[] {
  const parameters = route.parameters;
  if (!Array.isArray(parameters)) return [];
  return parameters.filter((item): item is RouteParameter => Boolean(item && typeof item === 'object'));
}

function routeBodyFields(route: Record<string, unknown>): string[] {
  const requestBody = route.request_body;
  if (!requestBody || typeof requestBody !== 'object') return [];
  const body = requestBody as Record<string, unknown>;
  const schema = body.schema;
  if (schema && typeof schema === 'object') {
    const properties = (schema as Record<string, unknown>).properties;
    if (properties && typeof properties === 'object') {
      return Object.keys(properties);
    }
  }
  const fields = body.fields;
  if (Array.isArray(fields)) {
    return fields
      .map((field) => String((field as RouteParameter).name ?? ''))
      .filter(Boolean);
  }
  return [];
}

function formatParameterTag(parameter: RouteParameter): string {
  const location = String(parameter.in ?? 'param');
  const name = String(parameter.name ?? '');
  const required = parameter.required ? ' 必填' : '';
  return `${location} ${name}${required}`;
}

function analysisStatusForSummaries(summaries: IndexSummary[]): string {
  if (!summaries.length) return '暂无记录';
  if (summaries.some((summary) => summary.exists === false)) return '部分路径不可用';
  return summaries.some((summary) => summary.analysis || summary.routes?.length || summary.dom_targets?.length)
    ? '可用'
    : '未分析';
}

function formatLatestAnalyzedAt(summaries: IndexSummary[]): string {
  const latest = summaries
    .map((summary) => summary.analysis?.analyzed_at)
    .filter((value): value is string => typeof value === 'string')
    .map((value) => ({ value, time: Date.parse(value) }))
    .filter((item) => Number.isFinite(item.time))
    .sort((left, right) => right.time - left.time)[0];
  return latest ? formatAnalyzedAt({ analyzed_at: latest.value }) : '暂无记录';
}

function formatAnalyzedAt(analysis: Record<string, unknown> | undefined): string {
  const raw = analysis?.analyzed_at;
  if (typeof raw !== 'string') return '暂无记录';
  return new Date(raw).toLocaleString('zh-CN', { hour12: false });
}
