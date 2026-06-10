import { Alert, Button, Empty, Flex, List, Segmented, Space, Spin, Tag, Tooltip, Typography } from 'antd';
import { GitBranch, RefreshCw } from 'lucide-react';
import { useMemo, useState } from 'react';

import type {
  KnowledgeGraphModule,
  KnowledgeGraphRelationship,
  ProjectKnowledgeGraph
} from '../types/projectKnowledgeGraph';
import {
  KnowledgeEvidenceDetailModal,
  buildRelationshipEvidenceDetail,
  buildRouteEvidenceDetail,
  buildTextEvidenceDetail,
  type KnowledgeEvidenceDetail
} from './KnowledgeGraphEvidenceDetail';
import {
  EvidenceCards,
  ModuleReviewEditor,
  ModuleRouteList,
  RelationshipCard,
  reviewStatusTag
} from './ProjectKnowledgeGraphCards';
import { ProjectKnowledgeGraphToolbar } from './ProjectKnowledgeGraphToolbar';
import './projectKnowledgeGraph.css';

const { Text } = Typography;

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
  const [evidenceDetail, setEvidenceDetail] = useState<KnowledgeEvidenceDetail | null>(null);
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
      <ProjectKnowledgeGraphToolbar
        modules={modules}
        relationshipCount={relationships.length}
        isReviewed={isReviewed}
        saving={saving}
        selectedModuleId={selectedModule?.id ?? null}
        onSelectModule={handleSelectModule}
        onReload={onReload}
        onRebuild={onRebuild}
        onApprove={onApprove}
      />

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
                  onOpenDetail={() => setEvidenceDetail(buildRelationshipEvidenceDetail(relationship))}
                  onOpenEvidence={(item, evidenceIndex) => setEvidenceDetail(buildTextEvidenceDetail({
                    title: '链路证据',
                    subtitle: relationship.variable ? `变量：${relationship.variable}` : relationship.reason,
                    evidence: item,
                    evidenceIndex,
                    allEvidence: relationship.evidence ?? [],
                    relationship
                  }))}
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
                onOpenRoute={(route) => setEvidenceDetail(buildRouteEvidenceDetail(route, selectedModule.name))}
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
                  onOpenRoute={(route) => setEvidenceDetail(buildRouteEvidenceDetail(route, selectedModule.name))}
                  onOpenModuleEvidence={(item, evidenceIndex) => setEvidenceDetail(buildTextEvidenceDetail({
                    title: '模块证据',
                    subtitle: selectedModule.name,
                    evidence: item,
                    evidenceIndex,
                    allEvidence: selectedModule.evidence ?? []
                  }))}
                  onOpenRouteEvidence={(route, item, evidenceIndex) => setEvidenceDetail(buildTextEvidenceDetail({
                    title: '接口证据',
                    subtitle: `${route.method ?? 'GET'} ${route.path ?? '/'}`,
                    evidence: item,
                    evidenceIndex,
                    allEvidence: route.evidence ?? [],
                    route
                  }))}
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
      <KnowledgeEvidenceDetailModal
        detail={evidenceDetail}
        onClose={() => setEvidenceDetail(null)}
      />
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
