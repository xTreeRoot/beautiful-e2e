import { Empty, Flex, Input, Space, Tabs, Tag, Tooltip, Typography } from 'antd';
import {
  Boxes,
  FileCode2,
  GitBranch,
  LocateFixed,
  MousePointerClick,
  Route,
  Search,
  Star
} from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';

import type { DomModuleCompileMode, Repository } from '../api';
import {
  buildDomTargetGraph,
  domFileName,
  domKindEntries,
  domKindLabel,
  filterDomTargetGraph,
  type DomCompileProgressState,
  type DomFileGroup,
  type DomRepositoryGroup,
  type DomTargetNode
} from '../lib/domTargetGraph';
import { DomPagePreviewCard } from './DomPagePreviewCard';
import './projectDomGraph.css';

const { Paragraph, Text, Title } = Typography;

type ProjectDomGraphPanelProps = {
  repositories: Repository[];
  compileProgress?: DomCompileProgressState | null;
  onCompileModule?: (module: DomFileGroup, mode: DomModuleCompileMode) => void;
};

type ModuleKindTab = 'page' | 'component';

type DomRelationship = {
  id: string;
  from: DomTargetNode;
  to: DomTargetNode;
  reason: string;
};

export function ProjectDomGraphPanel({
  repositories,
  compileProgress,
  onCompileModule
}: ProjectDomGraphPanelProps) {
  const [keyword, setKeyword] = useState('');
  const [moduleTab, setModuleTab] = useState<ModuleKindTab>('page');
  const [selectedModuleId, setSelectedModuleId] = useState<string | null>(null);
  const [selectedTargetId, setSelectedTargetId] = useState<string | null>(null);
  const graph = useMemo(() => buildDomTargetGraph(repositories), [repositories]);
  const visibleGraph = useMemo(() => filterDomTargetGraph(graph, keyword), [graph, keyword]);
  const visibleModules = useMemo(
    () => visibleGraph.files.filter((file) => file.moduleType === moduleTab),
    [moduleTab, visibleGraph.files]
  );
  const visibleRepositories = useMemo(
    () => repositoriesForFiles(visibleGraph.repositories, visibleModules),
    [visibleGraph.repositories, visibleModules]
  );
  const selectedModule = useMemo(
    () => visibleModules.find((file) => file.id === selectedModuleId) ?? visibleModules[0] ?? null,
    [selectedModuleId, visibleModules]
  );
  const selectedTarget = useMemo(
    () => (
      selectedModule?.targets.find((target) => target.id === selectedTargetId)
      ?? entrypointTargetsForModule(selectedModule)[0]
      ?? selectedModule?.targets[0]
      ?? null
    ),
    [selectedModule, selectedTargetId]
  );

  const handleSelectModule = (module: DomFileGroup) => {
    setSelectedModuleId(module.id);
    setSelectedTargetId(entrypointTargetsForModule(module)[0]?.id ?? module.targets[0]?.id ?? null);
  };

  if (!graph.targets.length) {
    return (
      <div className="dom-graph-empty">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 DOM 图谱" />
      </div>
    );
  }

  return (
    <div className="dom-graph-shell">
      <Flex align="center" justify="space-between" gap={12} className="dom-graph-toolbar">
        <Input
          allowClear
          className="dom-graph-search"
          prefix={<Search size={15} aria-hidden="true" />}
          placeholder="搜索 DOM 模块、入口、selector、代码片段或来源"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
        />
        <Space size={8} wrap className="dom-graph-summary">
          <Tag>{visibleGraph.files.length} 页面/组件</Tag>
          <Tag>{visibleGraph.targets.length} / {graph.targets.length} 目标</Tag>
          <Tag>{visibleGraph.files.filter((item) => item.moduleType === 'page').length} 页面</Tag>
        </Space>
      </Flex>

      {visibleGraph.targets.length ? (
        <div className="dom-graph-layout">
          <aside className="dom-graph-column" aria-label="页面模块">
            <Flex align="center" justify="space-between" className="dom-graph-column-title">
              <Text className="field-label">页面模块</Text>
              <Tag>{visibleModules.length}</Tag>
            </Flex>
            <Tabs
              className="dom-module-tabs"
              activeKey={moduleTab}
              onChange={(key) => {
                setModuleTab(key as ModuleKindTab);
                setSelectedModuleId(null);
                setSelectedTargetId(null);
              }}
              items={[
                {
                  key: 'page',
                  label: `页面 ${visibleGraph.files.filter((file) => file.moduleType === 'page').length}`,
                  children: (
                    <DomModuleList
                      repositories={visibleRepositories}
                      selectedModuleId={selectedModule?.id ?? null}
                      onSelectModule={handleSelectModule}
                    />
                  )
                },
                {
                  key: 'component',
                  label: `组件 ${visibleGraph.files.filter((file) => file.moduleType === 'component').length}`,
                  children: (
                    <DomModuleList
                      repositories={visibleRepositories}
                      selectedModuleId={selectedModule?.id ?? null}
                      onSelectModule={handleSelectModule}
                    />
                  )
                }
              ]}
            />
          </aside>

          <section className="dom-graph-column" aria-label="入口和链路关系">
            <Flex align="center" justify="space-between" className="dom-graph-column-title">
              <Text className="field-label">入口和链路关系</Text>
              <Tag>{relationshipsForModule(selectedModule).length}</Tag>
            </Flex>
            <DomRelationshipPanel
              module={selectedModule}
              selectedTargetId={selectedTarget?.id ?? null}
              onSelectTarget={setSelectedTargetId}
            />
          </section>

          <section className="dom-graph-column" aria-label="证据卡片">
            <Flex align="center" justify="space-between" className="dom-graph-column-title">
              <Text className="field-label">证据卡片</Text>
              {selectedModule ? <Tag>{selectedModule.targetCount}</Tag> : null}
            </Flex>
            <DomEvidencePanel
              module={selectedModule}
              target={selectedTarget}
              onSelectTarget={setSelectedTargetId}
              compileProgress={compileProgress}
              onCompileModule={onCompileModule}
            />
          </section>
        </div>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的 DOM 图谱节点" />
      )}
    </div>
  );
}

function DomModuleList({
  repositories,
  selectedModuleId,
  onSelectModule
}: {
  repositories: DomRepositoryGroup[];
  selectedModuleId: string | null;
  onSelectModule: (module: DomFileGroup) => void;
}) {
  return (
    <div className="dom-module-list">
      {repositories.map((repository) => (
        <div className="dom-repository-group" key={repository.id}>
          <Flex align="flex-start" justify="space-between" gap={8} className="dom-repository-head">
            <Flex vertical gap={3} className="dom-repository-copy">
              <Text strong>{repository.label}</Text>
              <Text className="analysis-path">{repository.kind}</Text>
            </Flex>
            <Tag>{repository.fileCount} 页面/组件</Tag>
          </Flex>
          <div className="dom-module-button-list">
            {repository.files.map((module) => (
              <button
                key={module.id}
                type="button"
                data-module-type={module.moduleType}
                className={module.id === selectedModuleId ? 'dom-module-card active' : 'dom-module-card'}
                onClick={() => onSelectModule(module)}
              >
                <span className="dom-card-icon" aria-hidden="true"><Boxes size={15} /></span>
                <span className="dom-module-copy">
                  <Text strong>{domFileName(module.path)}</Text>
                  <Text className="analysis-path">{module.moduleName}</Text>
                  <Space size={4} wrap className="dom-kind-tags">
                    <Tag color={module.moduleType === 'page' ? 'blue' : undefined}>
                      {module.moduleType === 'page' ? '页面' : '组件'}
                    </Tag>
                    <Tag>{entrypointTargetsForModule(module).length} 入口</Tag>
                    <Tag>{module.targetCount} 目标</Tag>
                    {domKindEntries(module.kindCounts).slice(0, 2).map(([kind, count]) => (
                      <Tag key={kind}>{domKindLabel(kind)} {count}</Tag>
                    ))}
                  </Space>
                </span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function DomRelationshipPanel({
  module,
  selectedTargetId,
  onSelectTarget
}: {
  module: DomFileGroup | null;
  selectedTargetId: string | null;
  onSelectTarget: (targetId: string) => void;
}) {
  if (!module) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 DOM 模块" />;
  }

  const entrypoints = entrypointTargetsForModule(module);
  const relationships = relationshipsForModule(module);

  return (
    <div className="dom-relationship-scroll">
      <div className="dom-scope-strip">
        <Text className="analysis-path">当前页面模块</Text>
        <Text strong>{module.moduleName}</Text>
        <Text className="analysis-path">{module.path}</Text>
      </div>

      <div className="dom-card-section">
        <Flex align="center" justify="space-between" className="dom-card-section-title">
          <Text className="field-label">入口候选</Text>
          <Tag>{entrypoints.length}</Tag>
        </Flex>
        {entrypoints.length ? entrypoints.map((target) => (
          <DomEntrypointCard
            key={target.id}
            target={target}
            active={target.id === selectedTargetId}
            onOpen={() => onSelectTarget(target.id)}
          />
        )) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无入口候选" />
        )}
      </div>

      <div className="dom-card-section">
        <Flex align="center" justify="space-between" className="dom-card-section-title">
          <Text className="field-label">链路关系</Text>
          <Tag>{relationships.length}</Tag>
        </Flex>
        {relationships.length ? relationships.map((relationship) => (
          <DomRelationshipCard
            key={relationship.id}
            relationship={relationship}
            active={relationship.to.id === selectedTargetId || relationship.from.id === selectedTargetId}
            onOpenTarget={onSelectTarget}
          />
        )) : (
          <DomTargetCardList
            targets={module.targets}
            selectedTargetId={selectedTargetId}
            onSelectTarget={onSelectTarget}
          />
        )}
      </div>
    </div>
  );
}

function DomEntrypointCard({
  target,
  active,
  onOpen
}: {
  target: DomTargetNode;
  active: boolean;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      className={active ? 'dom-entry-card active' : 'dom-entry-card'}
      onClick={onOpen}
    >
      <Flex align="center" gap={8} className="dom-entry-head">
        <Star size={15} aria-hidden="true" />
        <Text strong>{target.value}</Text>
        <Tag color="blue">入口</Tag>
        <Tag>{target.kindLabel}</Tag>
      </Flex>
      <Text className="analysis-source">{target.locator ?? target.source}</Text>
      {target.hint ? <Paragraph className="dom-card-note">{target.hint}</Paragraph> : null}
    </button>
  );
}

function DomRelationshipCard({
  relationship,
  active,
  onOpenTarget
}: {
  relationship: DomRelationship;
  active: boolean;
  onOpenTarget: (targetId: string) => void;
}) {
  return (
    <div className={active ? 'dom-relationship-card active' : 'dom-relationship-card'}>
      <button
        type="button"
        className="dom-card-open"
        onClick={() => onOpenTarget(relationship.to.id)}
      >
        <Flex align="center" gap={8} className="dom-route-flow">
          <GitBranch size={15} aria-hidden="true" />
          <Text strong>{relationship.to.kindLabel}</Text>
          <Tag>{stabilityLabel(relationship.to.stability)}</Tag>
        </Flex>
        <div className="dom-flow-line">
          <DomTargetRef target={relationship.from} />
          <span className="dom-flow-arrow">-&gt;</span>
          <DomTargetRef target={relationship.to} />
        </div>
        <Paragraph className="dom-card-note">{relationship.reason}</Paragraph>
      </button>
      <Space size={6} wrap className="dom-evidence-tags">
        <Tag>{relationship.to.source || relationship.to.filePath}</Tag>
        {relationship.to.locator ? <Tag>{relationship.to.locator}</Tag> : null}
      </Space>
    </div>
  );
}

function DomEvidencePanel({
  module,
  target,
  onSelectTarget,
  compileProgress,
  onCompileModule
}: {
  module: DomFileGroup | null;
  target: DomTargetNode | null;
  onSelectTarget: (targetId: string) => void;
  compileProgress?: DomCompileProgressState | null;
  onCompileModule?: (module: DomFileGroup, mode: DomModuleCompileMode) => void;
}) {
  if (!module) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无证据" />;
  }

  const groupedTargets = domKindEntries(module.kindCounts).map(([kind]) => ({
    kind,
    targets: module.targets.filter((item) => item.kind === kind)
  }));

  return (
    <div className="dom-evidence-scroll">
      <div className="dom-module-summary-card">
        <Title level={5}>{module.moduleName}</Title>
        <Paragraph className="dom-card-note">
          {module.moduleType === 'page'
            ? '该模块由页面入口证据归并而来，渲染预览来自系统内静态 DOM 草图。'
            : '该模块暂未发现页面路由，先按源码组件归并，后续可由页面渲染结果继续合并。'}
        </Paragraph>
        <Space size={6} wrap>
          <Tag>{module.repositoryName}</Tag>
          <Tag color={module.moduleType === 'page' ? 'blue' : undefined}>
            {module.moduleType === 'page' ? '页面模块' : '组件模块'}
          </Tag>
          <Tag>{module.targetCount} DOM 目标</Tag>
          <Tag>{entrypointTargetsForModule(module).length} 入口候选</Tag>
        </Space>
      </div>

      <DomPagePreviewCard
        module={module}
        compileProgress={compileProgress}
        onCompile={onCompileModule ? (mode) => onCompileModule(module, mode) : undefined}
      />

      {target ? <DomTargetDetailCard target={target} /> : null}

      <div className="dom-target-groups">
        {groupedTargets.map(({ kind, targets }) => (
          <div className="dom-target-group-card" key={kind}>
            <Flex align="center" justify="space-between" className="dom-target-group-head">
              <Space size={8}>
                {iconForDomKind(kind)}
                <Text strong>{domKindLabel(kind)}</Text>
              </Space>
              <Tag>{targets.length}</Tag>
            </Flex>
            <DomTargetCardList
              targets={targets}
              selectedTargetId={target?.id ?? null}
              onSelectTarget={onSelectTarget}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

function DomTargetDetailCard({ target }: { target: DomTargetNode }) {
  return (
    <div className="dom-target-detail-card">
      <Flex align="center" gap={8} className="dom-target-detail-head">
        <span className="dom-card-icon" aria-hidden="true">{iconForDomKind(target.kind)}</span>
        <span className="dom-target-detail-copy">
          <Text strong>{target.value}</Text>
          <Space size={6} wrap>
            <Tag>{target.kindLabel}</Tag>
            <Tag>{stabilityLabel(target.stability)}</Tag>
          </Space>
        </span>
      </Flex>
      <Fact label="推荐定位" value={target.locator ?? '暂无法生成稳定定位'} code />
      <Fact label="源码位置" value={target.source || target.filePath} code />
      {target.hint ? <Fact label="代码片段" value={target.hint} code multiline /> : null}
    </div>
  );
}

function DomTargetCardList({
  targets,
  selectedTargetId,
  onSelectTarget
}: {
  targets: DomTargetNode[];
  selectedTargetId: string | null;
  onSelectTarget: (targetId: string) => void;
}) {
  return (
    <div className="dom-target-card-list">
      {targets.map((target) => (
        <button
          key={target.id}
          type="button"
          className={target.id === selectedTargetId ? 'dom-target-card active' : 'dom-target-card'}
          onClick={() => onSelectTarget(target.id)}
        >
          <span className={`dom-target-stability ${target.stability}`} aria-hidden="true" />
          <span className="dom-target-card-copy">
            <Text strong>{target.value}</Text>
            <Text className="analysis-path">{target.locator ?? target.source}</Text>
          </span>
        </button>
      ))}
    </div>
  );
}

function DomTargetRef({ target }: { target: DomTargetNode }) {
  return (
    <span className="dom-target-ref">
      <Text strong>{target.kindLabel}</Text>
      <Text>{target.value}</Text>
    </span>
  );
}

function Fact({
  label,
  value,
  code = false,
  multiline = false
}: {
  label: string;
  value: string;
  code?: boolean;
  multiline?: boolean;
}) {
  return (
    <div className="dom-fact-row">
      <Text className="field-label">{label}</Text>
      {multiline ? (
        <pre className="dom-fact-code">{value}</pre>
      ) : (
        <Tooltip title={value}>
          <Text className={code ? 'dom-fact-value code' : 'dom-fact-value'}>{value}</Text>
        </Tooltip>
      )}
    </div>
  );
}

function entrypointTargetsForModule(module: DomFileGroup | null): DomTargetNode[] {
  if (!module) return [];
  const entryKinds = new Set(['route', 'testid', 'aria-label']);
  const primary = module.targets.filter((target) => entryKinds.has(target.kind));
  if (primary.length) return primary.slice(0, 8);
  return module.targets.filter((target) => target.stability !== 'low').slice(0, 4);
}

function relationshipsForModule(module: DomFileGroup | null): DomRelationship[] {
  if (!module) return [];
  const entrypoints = entrypointTargetsForModule(module);
  if (!entrypoints.length) return [];
  const primaryEntry = entrypoints[0];
  return module.targets
    .filter((target) => target.id !== primaryEntry.id)
    .slice(0, 24)
    .map((target) => ({
      id: `${primaryEntry.id}->${target.id}`,
      from: entrypoints.find((entry) => entry.kind === 'route') ?? primaryEntry,
      to: target,
      reason: relationshipReason(target)
    }));
}

function relationshipReason(target: DomTargetNode): string {
  if (target.kind === 'placeholder' || target.kind === 'name') {
    return '该目标看起来是表单输入或参数承载点，适合作为填充步骤或前置数据入口。';
  }
  if (target.kind === 'testid' || target.kind === 'aria-label') {
    return '该目标具备较稳定的自动化定位特征，适合作为点击、断言或关键状态锚点。';
  }
  if (target.kind === 'id') {
    return '该目标来自页面 id，稳定性需要结合源码语义复核，可作为候选定位。';
  }
  return '该目标与当前模块入口同源，可作为后续步骤或断言的候选证据。';
}

function iconForDomKind(kind: string): ReactNode {
  if (kind === 'route') return <Route size={15} aria-hidden="true" />;
  if (kind === 'testid' || kind === 'id') return <LocateFixed size={15} aria-hidden="true" />;
  if (kind === 'placeholder' || kind === 'name') return <MousePointerClick size={15} aria-hidden="true" />;
  return <FileCode2 size={15} aria-hidden="true" />;
}

function stabilityLabel(stability: DomTargetNode['stability']): string {
  if (stability === 'high') return '稳定优先';
  if (stability === 'medium') return '可用候选';
  return '弱候选';
}

function repositoriesForFiles(
  repositories: DomRepositoryGroup[],
  files: DomFileGroup[]
): DomRepositoryGroup[] {
  const fileIds = new Set(files.map((file) => file.id));
  return repositories
    .map((repository) => {
      const repositoryFiles = repository.files.filter((file) => fileIds.has(file.id));
      const targets = repositoryFiles.flatMap((file) => file.targets);
      return {
        ...repository,
        files: repositoryFiles,
        fileCount: repositoryFiles.length,
        targetCount: targets.length
      };
    })
    .filter((repository) => repository.files.length > 0);
}
