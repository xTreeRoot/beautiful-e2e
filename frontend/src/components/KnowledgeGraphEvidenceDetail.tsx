import { Empty, Flex, Modal, Space, Tag, Typography } from 'antd';
import { FileText, GitBranch, Route } from 'lucide-react';
import type { MouseEvent } from 'react';

import type {
  KnowledgeGraphRelationship,
  KnowledgeGraphRoute,
  KnowledgeGraphRouteRef
} from '../types/projectKnowledgeGraph';

const { Paragraph, Text } = Typography;

type RouteLike = KnowledgeGraphRoute | KnowledgeGraphRouteRef | undefined;

type DetailTagGroup = {
  label: string;
  values: string[];
  color?: string;
};

export type KnowledgeEvidenceDetail = {
  kind: 'relationship' | 'route' | 'evidence';
  title: string;
  subtitle?: string | null;
  route?: KnowledgeGraphRoute;
  relationship?: KnowledgeGraphRelationship;
  evidence: string[];
  focusedEvidence?: string;
  focusedEvidenceIndex?: number;
  tagGroups?: DetailTagGroup[];
};

type EvidenceListProps = {
  evidence?: string[];
  limit?: number;
  activeIndex?: number;
  onOpenEvidence?: (item: string, index: number) => void;
};

type TextEvidenceDetailOptions = {
  title: string;
  subtitle?: string | null;
  evidence: string;
  evidenceIndex: number;
  allEvidence: string[];
  route?: KnowledgeGraphRoute;
  relationship?: KnowledgeGraphRelationship;
};

/**
 * 生成链路详情弹窗的数据，保留完整证据列表，避免卡片区为了展示长文本产生横向滚动。
 */
export function buildRelationshipEvidenceDetail(
  relationship: KnowledgeGraphRelationship
): KnowledgeEvidenceDetail {
  return {
    kind: 'relationship',
    title: relationship.variable ? `变量链路：${relationship.variable}` : '变量链路详情',
    subtitle: relationship.reason,
    relationship,
    evidence: relationship.evidence ?? []
  };
}

/**
 * 生成接口详情弹窗的数据，卡片只展示摘要，完整字段和源码位置放在弹窗中查看。
 */
export function buildRouteEvidenceDetail(
  route: KnowledgeGraphRoute,
  moduleName?: string
): KnowledgeEvidenceDetail {
  return {
    kind: 'route',
    title: routeTitle(route),
    subtitle: moduleName ? `${moduleName}${route.summary ? ` / ${route.summary}` : ''}` : route.summary,
    route,
    evidence: route.evidence ?? [],
    tagGroups: routeTagGroups(route)
  };
}

/**
 * 生成单条证据详情弹窗的数据，同时携带上下文里的其他证据，方便人工复核来源。
 */
export function buildTextEvidenceDetail({
  title,
  subtitle,
  evidence,
  evidenceIndex,
  allEvidence,
  route,
  relationship
}: TextEvidenceDetailOptions): KnowledgeEvidenceDetail {
  return {
    kind: 'evidence',
    title,
    subtitle,
    route,
    relationship,
    evidence: allEvidence,
    focusedEvidence: evidence,
    focusedEvidenceIndex: evidenceIndex,
    tagGroups: route ? routeTagGroups(route) : undefined
  };
}

export function KnowledgeEvidenceDetailModal({
  detail,
  onClose
}: {
  detail: KnowledgeEvidenceDetail | null;
  onClose: () => void;
}) {
  return (
    <Modal
      className="knowledge-evidence-modal"
      title={detail?.title ?? '证据详情'}
      open={Boolean(detail)}
      footer={null}
      width={760}
      onCancel={onClose}
      destroyOnClose
    >
      {detail ? <KnowledgeEvidenceDetailBody detail={detail} /> : null}
    </Modal>
  );
}

export function EvidenceList({
  evidence,
  limit = 6,
  activeIndex,
  onOpenEvidence
}: EvidenceListProps) {
  const items = evidence ?? [];
  if (!items.length) {
    return <Text className="analysis-path">暂无证据</Text>;
  }

  const visibleItems = items.slice(0, limit);
  return (
    <div className="knowledge-evidence-lines">
      {visibleItems.map((item, index) => {
        const active = index === activeIndex;
        if (!onOpenEvidence) {
          return (
            <span
              key={`${item}-${index}`}
              className={active ? 'knowledge-evidence-line active' : 'knowledge-evidence-line'}
            >
              {item}
            </span>
          );
        }
        return (
          <button
            key={`${item}-${index}`}
            type="button"
            className={active ? 'knowledge-evidence-line active interactive' : 'knowledge-evidence-line interactive'}
            onClick={(event: MouseEvent<HTMLButtonElement>) => {
              event.stopPropagation();
              onOpenEvidence(item, index);
            }}
          >
            {item}
          </button>
        );
      })}
      {items.length > visibleItems.length ? (
        <Text className="knowledge-evidence-more">还有 {items.length - visibleItems.length} 条证据，可点开任意一条查看完整上下文</Text>
      ) : null}
    </div>
  );
}

export function knowledgeRouteRoleLabel(role: string | null | undefined): string {
  const map: Record<string, string> = {
    discovery: '发现',
    detail: '详情',
    action: '动作',
    request: '请求'
  };
  return map[role ?? ''] ?? '请求';
}

function KnowledgeEvidenceDetailBody({ detail }: { detail: KnowledgeEvidenceDetail }) {
  return (
    <div className="knowledge-evidence-modal-body">
      {detail.subtitle ? <Paragraph className="knowledge-evidence-modal-summary">{detail.subtitle}</Paragraph> : null}
      {detail.focusedEvidence ? (
        <section className="knowledge-evidence-modal-section">
          <Text className="field-label">当前证据</Text>
          <Paragraph className="knowledge-evidence-full">{detail.focusedEvidence}</Paragraph>
        </section>
      ) : null}
      {detail.relationship ? <RelationshipDetail relationship={detail.relationship} /> : null}
      {detail.route ? <RouteDetail route={detail.route} tagGroups={detail.tagGroups ?? []} /> : null}
      <section className="knowledge-evidence-modal-section">
        <Flex align="center" justify="space-between">
          <Text className="field-label">全部证据</Text>
          <Tag>{detail.evidence.length}</Tag>
        </Flex>
        {detail.evidence.length ? (
          <EvidenceList
            evidence={detail.evidence}
            limit={detail.evidence.length}
            activeIndex={detail.focusedEvidenceIndex}
          />
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无证据" />
        )}
      </section>
    </div>
  );
}

function RelationshipDetail({ relationship }: { relationship: KnowledgeGraphRelationship }) {
  return (
    <section className="knowledge-evidence-modal-section">
      <Flex align="center" gap={8}>
        <GitBranch size={16} aria-hidden="true" />
        <Text className="field-label">链路关系</Text>
        {relationship.confidence ? <Tag color="blue">置信度 {Math.round(relationship.confidence * 100)}%</Tag> : null}
      </Flex>
      <div className="knowledge-evidence-flow-detail">
        <RouteDetailLine label="生产方" route={relationship.from_route} />
        <RouteDetailLine label="消费方" route={relationship.to_route} />
      </div>
      {relationship.reason ? <Paragraph className="knowledge-evidence-full">{relationship.reason}</Paragraph> : null}
    </section>
  );
}

function RouteDetail({
  route,
  tagGroups
}: {
  route: KnowledgeGraphRoute;
  tagGroups: DetailTagGroup[];
}) {
  const sourceValues = [
    route.handler ? `处理器：${route.handler}` : null,
    route.source ? `来源：${route.source}` : null,
    route.source_file ? `文件：${route.source_file}${route.source_line ? `:${route.source_line}` : ''}` : null
  ].filter((value): value is string => Boolean(value));

  return (
    <section className="knowledge-evidence-modal-section">
      <Flex align="center" gap={8}>
        <Route size={16} aria-hidden="true" />
        <Text className="field-label">接口信息</Text>
        <Tag>{knowledgeRouteRoleLabel(route.role)}</Tag>
      </Flex>
      <RouteDetailLine route={route} />
      {route.summary ? <Paragraph className="knowledge-evidence-full">{route.summary}</Paragraph> : null}
      {tagGroups.map((group) => (
        <DetailTagGroup key={group.label} group={group} />
      ))}
      {sourceValues.length ? (
        <div className="knowledge-evidence-source">
          <FileText size={15} aria-hidden="true" />
          <Space direction="vertical" size={3}>
            {sourceValues.map((value) => <Text key={value}>{value}</Text>)}
          </Space>
        </div>
      ) : null}
    </section>
  );
}

function RouteDetailLine({
  label,
  route
}: {
  label?: string;
  route?: RouteLike;
}) {
  return (
    <div className="knowledge-route-detail-line">
      {label ? <Text className="analysis-path">{label}</Text> : null}
      <Text strong>{routeTitle(route)}</Text>
      {route?.summary ? <Text className="analysis-path">{route.summary}</Text> : null}
      {route?.source_file ? (
        <Text className="analysis-path">{`${route.source_file}${route.source_line ? `:${route.source_line}` : ''}`}</Text>
      ) : null}
    </div>
  );
}

function DetailTagGroup({ group }: { group: DetailTagGroup }) {
  if (!group.values.length) return null;
  return (
    <div className="knowledge-evidence-tag-group">
      <Text className="analysis-path">{group.label}</Text>
      <Space size={6} wrap>
        {group.values.map((value) => <Tag key={value} color={group.color}>{value}</Tag>)}
      </Space>
    </div>
  );
}

function routeTagGroups(route: KnowledgeGraphRoute): DetailTagGroup[] {
  return [
    { label: '产出变量', values: route.produces ?? [], color: 'blue' },
    { label: '消费变量', values: route.consumes ?? [], color: 'purple' },
    { label: '请求体字段', values: route.request_body_fields ?? [] },
    { label: '适用场景', values: route.applicable_scenarios ?? [], color: 'green' },
    { label: '排除场景', values: route.excluded_scenarios ?? [], color: 'orange' }
  ];
}

function routeTitle(route: RouteLike): string {
  return `${route?.method ?? 'GET'} ${route?.path ?? '/'}`;
}
