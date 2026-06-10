import { Button, Flex, Input, Space, Tag, Tooltip, Typography } from 'antd';
import { Ban, CheckCircle2, Route, Save, Star, StarOff } from 'lucide-react';
import { useEffect, useState } from 'react';

import type {
  KnowledgeGraphModule,
  KnowledgeGraphRelationship,
  KnowledgeGraphRoute
} from '../types/projectKnowledgeGraph';
import { EvidenceList, knowledgeRouteRoleLabel } from './KnowledgeGraphEvidenceDetail';

const { Paragraph, Text, Title } = Typography;

export function RelationshipCard({
  relationship,
  graphReviewed,
  saving,
  onOpenDetail,
  onOpenEvidence,
  onConfirm,
  onReject
}: {
  relationship: KnowledgeGraphRelationship;
  graphReviewed: boolean;
  saving: boolean;
  onOpenDetail: () => void;
  onOpenEvidence: (item: string, evidenceIndex: number) => void;
  onConfirm: () => void;
  onReject: () => void;
}) {
  const isRejected = relationship.review_status === 'rejected';
  const isConfirmed = !isRejected && (graphReviewed || relationship.confirmed || relationship.review_status === 'reviewed');
  return (
    <div className={isRejected ? 'knowledge-relationship-card rejected' : 'knowledge-relationship-card'}>
      <button
        type="button"
        className="knowledge-card-open"
        onClick={onOpenDetail}
      >
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
      </button>
      <EvidenceList evidence={relationship.evidence ?? []} onOpenEvidence={onOpenEvidence} />
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

export function ModuleRouteList({
  module,
  graphReviewed,
  saving,
  onOpenRoute,
  onToggleEntrypoint
}: {
  module: KnowledgeGraphModule;
  graphReviewed: boolean;
  saving: boolean;
  onOpenRoute: (route: KnowledgeGraphRoute) => void;
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
          onOpenDetail={() => onOpenRoute(route)}
          onToggleEntrypoint={(enabled) => onToggleEntrypoint(route.id, enabled)}
        />
      ))}
    </div>
  );
}

export function ModuleReviewEditor({
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

export function EvidenceCards({
  module,
  graphReviewed,
  saving,
  onOpenRoute,
  onOpenModuleEvidence,
  onOpenRouteEvidence,
  onToggleEntrypoint
}: {
  module: KnowledgeGraphModule;
  graphReviewed: boolean;
  saving: boolean;
  onOpenRoute: (route: KnowledgeGraphRoute) => void;
  onOpenModuleEvidence: (item: string, evidenceIndex: number) => void;
  onOpenRouteEvidence: (route: KnowledgeGraphRoute, item: string, evidenceIndex: number) => void;
  onToggleEntrypoint: (routeId: string, enabled: boolean) => void;
}) {
  const entrypoints = new Set(module.entrypoint_route_ids ?? []);
  return (
    <div className="knowledge-evidence-list">
      <Title level={5}>{module.name}</Title>
      {module.scope_boundary ? <Paragraph className="knowledge-graph-note">{module.scope_boundary}</Paragraph> : null}
      <EvidenceList evidence={module.evidence ?? []} onOpenEvidence={onOpenModuleEvidence} />
      {(module.routes ?? []).map((route) => (
        <RouteCard
          key={route.id}
          route={route}
          isEntrypoint={entrypoints.has(route.id)}
          graphReviewed={graphReviewed}
          saving={saving}
          showEvidence
          onOpenDetail={() => onOpenRoute(route)}
          onOpenEvidence={(item, evidenceIndex) => onOpenRouteEvidence(route, item, evidenceIndex)}
          onToggleEntrypoint={(enabled) => onToggleEntrypoint(route.id, enabled)}
        />
      ))}
    </div>
  );
}

export function reviewStatusTag(status: string | null | undefined, graphReviewed = false) {
  if (status === 'rejected') {
    return <Tag color="red">已排除</Tag>;
  }
  if (graphReviewed || status === 'reviewed') {
    return <Tag color="green">已审核</Tag>;
  }
  return <Tag color="gold">待审核</Tag>;
}

function RouteCard({
  route,
  isEntrypoint,
  graphReviewed,
  saving,
  showEvidence,
  onOpenDetail,
  onOpenEvidence,
  onToggleEntrypoint
}: {
  route: KnowledgeGraphRoute;
  isEntrypoint: boolean;
  graphReviewed: boolean;
  saving: boolean;
  showEvidence?: boolean;
  onOpenDetail: () => void;
  onOpenEvidence?: (item: string, evidenceIndex: number) => void;
  onToggleEntrypoint: (enabled: boolean) => void;
}) {
  return (
    <div className="knowledge-route-card">
      <Flex align="flex-start" justify="space-between" gap={8} className="knowledge-route-card-head">
        <button type="button" className="knowledge-card-open knowledge-route-open" onClick={onOpenDetail}>
          <Text strong>{`${route.method ?? 'GET'} ${route.path ?? '/'}`}</Text>
          {route.summary ? <Text className="analysis-path">{route.summary}</Text> : null}
          <RouteTags route={route} />
        </button>
        <Space size={6}>
          {isEntrypoint ? <Tag color="blue">入口</Tag> : <Tag>{knowledgeRouteRoleLabel(route.role)}</Tag>}
          {reviewStatusTag(route.review_status, graphReviewed)}
          <Tooltip title={isEntrypoint ? '取消入口标记' : '标记为入口'}>
            <Button
              className="icon-button"
              aria-label={isEntrypoint ? '取消入口标记' : '标记为入口'}
              icon={isEntrypoint ? <StarOff size={14} /> : <Star size={14} />}
              disabled={saving}
              onClick={(event) => {
                event.stopPropagation();
                onToggleEntrypoint(!isEntrypoint);
              }}
            />
          </Tooltip>
        </Space>
      </Flex>
      {showEvidence ? <EvidenceList evidence={route.evidence ?? []} onOpenEvidence={onOpenEvidence} /> : null}
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

function RouteRef({ route }: { route?: KnowledgeGraphRelationship['from_route'] }) {
  return (
    <span className="knowledge-route-ref">
      <Text strong>{route?.method ?? 'GET'}</Text>
      <Text>{route?.path ?? '/'}</Text>
    </span>
  );
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
