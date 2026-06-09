import { Alert, Button, Empty, Flex, Input, List, Segmented, Space, Spin, Tag, Tooltip, Typography } from 'antd';
import { Ban, CheckCircle2, GitBranch, RefreshCw, Route, Save, ShieldCheck, Star, StarOff } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import type {
  KnowledgeGraphModule,
  KnowledgeGraphRelationship,
  KnowledgeGraphRoute,
  ProjectKnowledgeGraph
} from '../types/projectKnowledgeGraph';
import './projectKnowledgeGraph.css';

const { Paragraph, Text, Title } = Typography;

type ProjectKnowledgeGraphPanelProps = {
  graph: ProjectKnowledgeGraph | null;
  loading: boolean;
  saving: boolean;
  error: string | null;
  onReload: () => void;
  onRebuild: () => void;
  onSaveGraph: (nextGraph: ProjectKnowledgeGraph['graph'], reviewStatus?: string) => void;
  onApprove: () => void;
};

type RelationshipScope = 'module' | 'all';

export function ProjectKnowledgeGraphPanel({
  graph,
  loading,
  saving,
  error,
  onReload,
  onRebuild,
  onSaveGraph,
  onApprove
}: ProjectKnowledgeGraphPanelProps) {
  const modules = graph?.graph.modules ?? [];
  const relationships = graph?.graph.relationships ?? [];
  const [selectedModuleId, setSelectedModuleId] = useState<string | null>(null);
  const [relationshipScope, setRelationshipScope] = useState<RelationshipScope>('module');
  const selectedModule = useMemo(
    () => modules.find((module) => module.id === selectedModuleId) ?? modules[0] ?? null,
    [modules, selectedModuleId]
  );
  const visibleRelationships = useMemo(
    () => (
      relationshipScope === 'module'
        ? relationshipsForModule(relationships, selectedModule?.id)
        : relationships.slice(0, 80)
    ),
    [relationshipScope, relationships, selectedModule]
  );
  const isReviewed = graph?.review_status === 'reviewed';
  const handleSelectModule = (moduleId: string) => {
    setSelectedModuleId(moduleId);
    setRelationshipScope('module');
  };
  const handleSaveGraph = (nextGraph: ProjectKnowledgeGraph['graph']) => {
    if (!graph) return;
    onSaveGraph(nextGraph, graph.review_status);
  };
  const handleUpdateModule = (moduleId: string, patch: Partial<KnowledgeGraphModule>) => {
    if (!graph) return;
    handleSaveGraph(updateModulePayload(graph.graph, moduleId, (module) => ({ ...module, ...patch })));
  };
  const handleToggleEntrypoint = (moduleId: string, routeId: string, enabled: boolean) => {
    if (!graph) return;
    handleSaveGraph(toggleEntrypointPayload(graph.graph, moduleId, routeId, enabled, isReviewed));
  };
  const handleUpdateRelationship = (
    relationshipId: string,
    patch: Partial<KnowledgeGraphRelationship>
  ) => {
    if (!graph) return;
    handleSaveGraph(updateRelationshipPayload(graph.graph, relationshipId, patch));
  };

  if (loading) {
    return (
      <div className="knowledge-graph-loading">
        <Spin />
        <Text className="analysis-path">正在读取项目知识图谱</Text>
      </div>
    );
  }

  if (!graph) {
    return (
      <div className="knowledge-graph-empty">
        {error ? <Alert type="warning" showIcon message={error} /> : null}
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无项目知识图谱">
          <Button
            type="primary"
            className="primary-button"
            icon={<RefreshCw size={16} />}
            loading={saving}
            onClick={onRebuild}
          >
            重建候选图谱
          </Button>
        </Empty>
      </div>
    );
  }

  return (
    <div className="knowledge-graph-shell">
      <Flex className="knowledge-graph-toolbar" align="center" justify="space-between" gap={12}>
        <Space size={8} wrap>
          <Tag color={isReviewed ? 'green' : 'gold'}>{isReviewed ? '已审核强事实' : '候选事实'}</Tag>
          <Tag>{modules.length} 个模块</Tag>
          <Tag>{relationships.length} 条关系</Tag>
        </Space>
        <Space size={8} wrap>
          <Tooltip title="刷新图谱">
            <Button
              className="icon-button"
              aria-label="刷新图谱"
              icon={<RefreshCw size={16} />}
              onClick={onReload}
            />
          </Tooltip>
          <Button className="secondary-button" icon={<GitBranch size={16} />} loading={saving} onClick={onRebuild}>
            重建候选
          </Button>
          <Button
            type="primary"
            className="primary-button"
            icon={<ShieldCheck size={16} />}
            loading={saving}
            disabled={isReviewed}
            onClick={onApprove}
          >
            批准图谱
          </Button>
        </Space>
      </Flex>

      {error ? <Alert className="knowledge-graph-alert" type="warning" showIcon message={error} /> : null}

      <div className="knowledge-graph-layout">
        <aside className="knowledge-graph-column" aria-label="模块树">
          <Flex align="center" justify="space-between" className="knowledge-graph-column-title">
            <Text className="field-label">模块树</Text>
            <Tag>{modules.length}</Tag>
          </Flex>
          {modules.length ? (
            <List
              className="knowledge-module-list"
              dataSource={modules}
              renderItem={(module) => (
                <List.Item
                  className={module.id === selectedModule?.id ? 'knowledge-module-row active' : 'knowledge-module-row'}
                  role="button"
                  tabIndex={0}
                  onClick={() => handleSelectModule(module.id)}
                  onKeyDown={(event) => {
                    if (event.key !== 'Enter' && event.key !== ' ') return;
                    event.preventDefault();
                    handleSelectModule(module.id);
                  }}
                >
                  <Flex align="flex-start" justify="space-between" gap={8} className="knowledge-module-main">
                    <Flex vertical gap={6} className="knowledge-module-copy">
                      <Text strong>{module.name}</Text>
                      <Text className="analysis-path">{module.repository_kind ?? 'repository'}</Text>
                      <Space size={6} wrap>
                        <Tag>{module.routes?.length ?? 0} 接口</Tag>
                        {reviewStatusTag(module.review_status, isReviewed)}
                        {module.id === selectedModule?.id ? <Tag color="blue">当前模块</Tag> : null}
                      </Space>
                    </Flex>
                    <Tooltip title="查看模块链路">
                      <Button
                        className="icon-button knowledge-module-action"
                        aria-label="查看模块链路"
                        icon={<GitBranch size={15} />}
                        onClick={(event) => {
                          event.stopPropagation();
                          handleSelectModule(module.id);
                        }}
                      />
                    </Tooltip>
                  </Flex>
                </List.Item>
              )}
            />
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无模块" />
          )}
        </aside>

        <section className="knowledge-graph-column" aria-label="链路图">
          <Flex align="center" justify="space-between" className="knowledge-graph-column-title">
            <Text className="field-label">链路图</Text>
            <Space size={8}>
              <Segmented
                size="small"
                value={relationshipScope}
                onChange={(value) => setRelationshipScope(value as RelationshipScope)}
                options={[
                  { value: 'module', label: '当前模块' },
                  { value: 'all', label: '全部关系' }
                ]}
              />
              <Tag>{visibleRelationships.length}</Tag>
            </Space>
          </Flex>
          <div className="knowledge-graph-scroll">
            {relationshipScope === 'module' && selectedModule ? (
              <div className="knowledge-scope-strip">
                <Text className="analysis-path">当前模块</Text>
                <Text strong>{selectedModule.name}</Text>
              </div>
            ) : null}
            {visibleRelationships.length ? (
              visibleRelationships.map((relationship) => (
                <RelationshipCard
                  key={relationship.id}
                  relationship={relationship}
                  graphReviewed={isReviewed}
                  saving={saving}
                  onConfirm={() => handleUpdateRelationship(
                    relationship.id,
                    { confirmed: true, review_status: 'reviewed' }
                  )}
                  onReject={() => handleUpdateRelationship(
                    relationship.id,
                    { confirmed: false, review_status: 'rejected' }
                  )}
                />
              ))
            ) : selectedModule ? (
              <ModuleRouteList
                module={selectedModule}
                graphReviewed={isReviewed}
                saving={saving}
                onToggleEntrypoint={(routeId, enabled) => handleToggleEntrypoint(
                  selectedModule.id,
                  routeId,
                  enabled
                )}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无链路关系" />
            )}
          </div>
        </section>

        <section className="knowledge-graph-column" aria-label="证据卡片">
          <Flex align="center" justify="space-between" className="knowledge-graph-column-title">
            <Text className="field-label">证据卡片</Text>
            <Tag>{selectedModule?.evidence?.length ?? 0}</Tag>
          </Flex>
          <div className="knowledge-graph-scroll">
            {selectedModule ? (
              <>
                <ModuleReviewEditor
                  module={selectedModule}
                  graphReviewed={isReviewed}
                  saving={saving}
                  onSave={(patch) => handleUpdateModule(selectedModule.id, patch)}
                />
                <EvidenceCards
                  module={selectedModule}
                  graphReviewed={isReviewed}
                  saving={saving}
                  onToggleEntrypoint={(routeId, enabled) => handleToggleEntrypoint(
                    selectedModule.id,
                    routeId,
                    enabled
                  )}
                />
              </>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择模块查看证据" />
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function RelationshipCard({
  relationship,
  graphReviewed,
  saving,
  onConfirm,
  onReject
}: {
  relationship: KnowledgeGraphRelationship;
  graphReviewed: boolean;
  saving: boolean;
  onConfirm: () => void;
  onReject: () => void;
}) {
  const isRejected = relationship.review_status === 'rejected';
  const isConfirmed = !isRejected && (graphReviewed || relationship.confirmed || relationship.review_status === 'reviewed');
  return (
    <div className={isRejected ? 'knowledge-relationship-card rejected' : 'knowledge-relationship-card'}>
      <Flex align="center" gap={8} className="knowledge-route-flow">
        <Route size={16} aria-hidden="true" />
        <Text strong>{relationship.variable ?? '变量'}</Text>
        {relationshipStatusTag(relationship, graphReviewed)}
      </Flex>
      <div className="knowledge-flow-line">
        <RouteRef route={relationship.from_route} />
        <span className="knowledge-flow-arrow">-&gt;</span>
        <RouteRef route={relationship.to_route} />
      </div>
      {relationship.reason ? <Paragraph className="knowledge-graph-note">{relationship.reason}</Paragraph> : null}
      <EvidenceList evidence={relationship.evidence ?? []} />
      <Space size={8} wrap className="knowledge-card-actions">
        <Button
          size="small"
          className="secondary-button"
          icon={<CheckCircle2 size={14} />}
          loading={saving && !isConfirmed}
          disabled={saving || isConfirmed}
          onClick={onConfirm}
        >
          确认关系
        </Button>
        <Button
          size="small"
          danger
          icon={<Ban size={14} />}
          loading={saving && !isRejected}
          disabled={saving || isRejected}
          onClick={onReject}
        >
          排除关系
        </Button>
      </Space>
    </div>
  );
}

function RouteRef({ route }: { route?: KnowledgeGraphRelationship['from_route'] }) {
  return (
    <span className="knowledge-route-ref">
      <Text strong>{route?.method ?? 'GET'}</Text>
      <Text>{route?.path ?? '/'}</Text>
    </span>
  );
}

function ModuleRouteList({
  module,
  graphReviewed,
  saving,
  onToggleEntrypoint
}: {
  module: KnowledgeGraphModule;
  graphReviewed: boolean;
  saving: boolean;
  onToggleEntrypoint: (routeId: string, enabled: boolean) => void;
}) {
  const entrypoints = new Set(module.entrypoint_route_ids ?? []);
  return (
    <div className="knowledge-route-list">
      {(module.routes ?? []).map((route) => (
        <RouteCard
          key={route.id}
          route={route}
          isEntrypoint={entrypoints.has(route.id)}
          graphReviewed={graphReviewed}
          saving={saving}
          onToggleEntrypoint={(enabled) => onToggleEntrypoint(route.id, enabled)}
        />
      ))}
    </div>
  );
}

function RouteCard({
  route,
  isEntrypoint,
  graphReviewed,
  saving,
  showEvidence,
  onToggleEntrypoint
}: {
  route: KnowledgeGraphRoute;
  isEntrypoint: boolean;
  graphReviewed: boolean;
  saving: boolean;
  showEvidence?: boolean;
  onToggleEntrypoint: (enabled: boolean) => void;
}) {
  return (
    <div className="knowledge-route-card">
      <Flex align="center" justify="space-between" gap={8}>
        <Text strong>{`${route.method ?? 'GET'} ${route.path ?? '/'}`}</Text>
        <Space size={6}>
          {isEntrypoint ? <Tag color="blue">入口</Tag> : <Tag>{roleLabel(route.role)}</Tag>}
          {reviewStatusTag(route.review_status, graphReviewed)}
          <Tooltip title={isEntrypoint ? '取消入口标记' : '标记为入口'}>
            <Button
              className="icon-button"
              aria-label={isEntrypoint ? '取消入口标记' : '标记为入口'}
              icon={isEntrypoint ? <StarOff size={14} /> : <Star size={14} />}
              disabled={saving}
              onClick={() => onToggleEntrypoint(!isEntrypoint)}
            />
          </Tooltip>
        </Space>
      </Flex>
      {route.summary ? <Text className="analysis-path">{route.summary}</Text> : null}
      <RouteTags route={route} />
      {showEvidence ? <EvidenceList evidence={route.evidence ?? []} /> : null}
    </div>
  );
}

function ModuleReviewEditor({
  module,
  graphReviewed,
  saving,
  onSave
}: {
  module: KnowledgeGraphModule;
  graphReviewed: boolean;
  saving: boolean;
  onSave: (patch: Partial<KnowledgeGraphModule>) => void;
}) {
  const [name, setName] = useState(module.name);
  const [scopeBoundary, setScopeBoundary] = useState(module.scope_boundary ?? '');
  const isDirty = name.trim() !== module.name || scopeBoundary.trim() !== (module.scope_boundary ?? '');

  useEffect(() => {
    setName(module.name);
    setScopeBoundary(module.scope_boundary ?? '');
  }, [module.id, module.name, module.scope_boundary]);

  return (
    <div className="knowledge-module-editor">
      <Flex align="center" justify="space-between" gap={8}>
        <Text className="field-label">人工校正</Text>
        {reviewStatusTag(module.review_status, graphReviewed)}
      </Flex>
      <label className="knowledge-editor-field">
        <Text className="analysis-path">模块名</Text>
        <Input
          value={name}
          maxLength={80}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <label className="knowledge-editor-field">
        <Text className="analysis-path">边界说明</Text>
        <Input.TextArea
          value={scopeBoundary}
          autoSize={{ minRows: 3, maxRows: 6 }}
          maxLength={400}
          onChange={(event) => setScopeBoundary(event.target.value)}
        />
      </label>
      <Button
        type="primary"
        className="primary-button"
        icon={<Save size={15} />}
        loading={saving}
        disabled={!isDirty || !name.trim()}
        onClick={() => onSave({
          name: name.trim(),
          scope_boundary: scopeBoundary.trim() || null,
          review_status: 'reviewed'
        })}
      >
        保存模块
      </Button>
    </div>
  );
}

function EvidenceCards({
  module,
  graphReviewed,
  saving,
  onToggleEntrypoint
}: {
  module: KnowledgeGraphModule;
  graphReviewed: boolean;
  saving: boolean;
  onToggleEntrypoint: (routeId: string, enabled: boolean) => void;
}) {
  const entrypoints = new Set(module.entrypoint_route_ids ?? []);
  return (
    <div className="knowledge-evidence-list">
      <Title level={5}>{module.name}</Title>
      {module.scope_boundary ? <Paragraph className="knowledge-graph-note">{module.scope_boundary}</Paragraph> : null}
      <EvidenceList evidence={module.evidence ?? []} />
      {(module.routes ?? []).map((route) => (
        <RouteCard
          key={route.id}
          route={route}
          isEntrypoint={entrypoints.has(route.id)}
          graphReviewed={graphReviewed}
          saving={saving}
          showEvidence
          onToggleEntrypoint={(enabled) => onToggleEntrypoint(route.id, enabled)}
        />
      ))}
    </div>
  );
}

function RouteTags({ route }: { route: KnowledgeGraphRoute }) {
  return (
    <Space size={6} wrap className="knowledge-route-tags">
      {(route.produces ?? []).map((value) => <Tag key={`p-${value}`}>产出 {value}</Tag>)}
      {(route.consumes ?? []).map((value) => <Tag key={`c-${value}`}>消费 {value}</Tag>)}
      {(route.excluded_scenarios ?? []).map((value) => <Tag key={`x-${value}`} color="orange">排除</Tag>)}
    </Space>
  );
}

function EvidenceList({ evidence }: { evidence: string[] }) {
  if (!evidence.length) {
    return <Text className="analysis-path">暂无证据</Text>;
  }
  return (
    <div className="knowledge-evidence-lines">
      {evidence.slice(0, 6).map((item) => (
        <Text key={item} className="knowledge-evidence-line">{item}</Text>
      ))}
    </div>
  );
}

function relationshipsForModule(
  relationships: KnowledgeGraphRelationship[],
  moduleId: string | null | undefined
): KnowledgeGraphRelationship[] {
  if (!moduleId) return relationships.slice(0, 12);
  return relationships
    .filter((relationship) => relationship.from_module === moduleId || relationship.to_module === moduleId)
    .slice(0, 24);
}

function updateModulePayload(
  graph: ProjectKnowledgeGraph['graph'],
  moduleId: string,
  updater: (module: KnowledgeGraphModule) => KnowledgeGraphModule
): ProjectKnowledgeGraph['graph'] {
  return {
    ...graph,
    modules: (graph.modules ?? []).map((module) => (
      module.id === moduleId ? updater(module) : module
    ))
  };
}

function toggleEntrypointPayload(
  graph: ProjectKnowledgeGraph['graph'],
  moduleId: string,
  routeId: string,
  enabled: boolean,
  graphReviewed: boolean
): ProjectKnowledgeGraph['graph'] {
  return updateModulePayload(graph, moduleId, (module) => {
    const current = new Set(module.entrypoint_route_ids ?? []);
    if (enabled) {
      current.add(routeId);
    } else {
      current.delete(routeId);
    }
    return {
      ...module,
      review_status: graphReviewed ? 'reviewed' : module.review_status,
      entrypoint_route_ids: Array.from(current),
      routes: (module.routes ?? []).map((route) => (
        route.id === routeId
          ? { ...route, review_status: 'reviewed' }
          : route
      ))
    };
  });
}

function updateRelationshipPayload(
  graph: ProjectKnowledgeGraph['graph'],
  relationshipId: string,
  patch: Partial<KnowledgeGraphRelationship>
): ProjectKnowledgeGraph['graph'] {
  return {
    ...graph,
    relationships: (graph.relationships ?? []).map((relationship) => (
      relationship.id === relationshipId
        ? { ...relationship, ...patch }
        : relationship
    ))
  };
}

function reviewStatusTag(status: string | null | undefined, graphReviewed = false) {
  if (status === 'rejected') {
    return <Tag color="red">已排除</Tag>;
  }
  if (graphReviewed || status === 'reviewed') {
    return <Tag color="green">已审核</Tag>;
  }
  return <Tag color="gold">待审核</Tag>;
}

function relationshipStatusTag(
  relationship: KnowledgeGraphRelationship,
  graphReviewed: boolean
) {
  if (relationship.review_status === 'rejected') {
    return <Tag color="red">已排除</Tag>;
  }
  if (graphReviewed || relationship.confirmed || relationship.review_status === 'reviewed') {
    return <Tag color="green">已确认</Tag>;
  }
  return <Tag color="gold">待审核</Tag>;
}

function roleLabel(role: string | null | undefined): string {
  const map: Record<string, string> = {
    discovery: '发现',
    detail: '详情',
    action: '动作',
    request: '请求'
  };
  return map[role ?? ''] ?? '请求';
}
