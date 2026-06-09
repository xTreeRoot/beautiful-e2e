import { Button, Empty, Flex, Input, List, Modal, Segmented, Space, Tag, Typography } from 'antd';
import { FileCode2, Network, RefreshCw, Search } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
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

export function ProjectAnalysisModal({
  open,
  project,
  loading,
  onClose,
  onRunAnalysis,
  showToast
}: ProjectAnalysisModalProps) {
  const repositories = project?.repositories ?? [];
  const [selectedRepositoryId, setSelectedRepositoryId] = useState<string | null>(null);
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

  useEffect(() => {
    if (!open) return;
    setSelectedRepositoryId((current) => {
      if (current && repositories.some((repo) => repo.id === current)) return current;
      return repositories[0]?.id ?? null;
    });
  }, [open, repositories]);

  const selectedRepository = useMemo(
    () => repositories.find((repo) => repo.id === selectedRepositoryId) ?? repositories[0],
    [repositories, selectedRepositoryId]
  );

  return (
    <Modal
      className="analysis-modal-shell"
      centered
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
      width={1800}
      footer={null}
    >
      <div className="analysis-modal-layout">
        <aside className="analysis-records" aria-label="分析记录">
          <Flex align="center" justify="space-between" className="analysis-panel-heading">
            <Text className="field-label">分析记录</Text>
            <Tag>{repositories.length}</Tag>
          </Flex>
          {repositories.length ? (
            <List
              dataSource={repositories}
              renderItem={(repo) => (
                <List.Item
                  className={repo.id === selectedRepository?.id ? 'analysis-record active' : 'analysis-record'}
                  onClick={() => {
                    setSelectedRepositoryId(repo.id);
                    setDetailView('overview');
                    setRouteSearch('');
                  }}
                >
                  <Flex vertical gap={6} className="analysis-record-main">
                    <Flex align="center" justify="space-between" gap={8}>
                      <Text strong>{formatRepositoryKind(repo.kind)}</Text>
                      <Tag>{analysisStatus(repo)}</Tag>
                    </Flex>
                    <Text className="analysis-path">{repo.path || '未配置路径'}</Text>
                    <Space size={6} wrap>
                      <Tag>{routeCount(repo)} 条接口</Tag>
                      <Tag>{domTargetCount(repo)} DOM</Tag>
                    </Space>
                  </Flex>
                </List.Item>
              )}
            />
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无分析记录" />
          )}
        </aside>

        <section className="analysis-detail" aria-label="分析详情">
          {detailView === 'graph' || selectedRepository ? (
            <>
              <Flex align="center" justify="space-between" gap={12} className="analysis-detail-title">
                <div>
                  <Title level={5}>
                    {detailView === 'graph' ? '项目知识图谱' : formatRepositoryKind(selectedRepository.kind)}
                  </Title>
                  <Text className="analysis-path">
                    {detailView === 'graph' ? project?.name ?? '当前项目' : selectedRepository.path}
                  </Text>
                </div>
                <Segmented
                  value={detailView}
                  onChange={(value) => setDetailView(value as DetailView)}
                  options={[
                    { value: 'overview', label: '概览' },
                    { value: 'graph', label: '图谱' },
                    { value: 'routes', label: '接口' },
                    { value: 'dom', label: 'DOM' },
                    { value: 'raw', label: '原始' }
                  ]}
                />
              </Flex>
              <AnalysisDetailContent
                repository={selectedRepository}
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
  repository,
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
  repository?: Repository;
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
  const summary = repository ? indexSummary(repository) : {};
  const routes = summary.routes ?? [];
  const domTargets = summary.dom_targets ?? [];
  const signals = summary.signals ?? [];
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

  if (!repository) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择一条分析记录查看详情" />;
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
        {JSON.stringify(repository.index_summary ?? {}, null, 2)}
      </pre>
    );
  }

  return (
    <div className="analysis-overview-grid">
      <Metric label="接口路由" value={routes.length} />
      <Metric label="DOM 目标" value={domTargets.length} />
      <Metric label="扫描文件" value={(summary.files ?? []).length} />
      <Metric label="分析状态" value={summary.exists === false ? '路径不可用' : '可用'} />
      <div className="analysis-overview-wide">
        <Text className="field-label">最近分析</Text>
        <Text>{formatAnalyzedAt(summary.analysis)}</Text>
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

function routeCount(repository: Repository): number {
  return indexSummary(repository).routes?.length ?? 0;
}

function domTargetCount(repository: Repository): number {
  return indexSummary(repository).dom_targets?.length ?? 0;
}

function analysisStatus(repository: Repository): string {
  return repository.index_summary ? '已分析' : '未分析';
}

function formatRepositoryKind(kind: string): string {
  const map: Record<string, string> = {
    workspace: '工作区',
    frontend: '前端',
    backend: '后端'
  };
  return map[kind] ?? kind;
}

function formatAnalyzedAt(analysis: Record<string, unknown> | undefined): string {
  const raw = analysis?.analyzed_at;
  if (typeof raw !== 'string') return '暂无记录';
  return new Date(raw).toLocaleString('zh-CN', { hour12: false });
}
