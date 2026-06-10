import { Button, Empty, Flex, Input, Space, Tag, Tooltip, Typography } from 'antd';
import { LocateFixed, Route, Search } from 'lucide-react';
import { useMemo, useState } from 'react';

import {
  type KnowledgeGraphRouteSearchResult,
  routeLabel,
  searchKnowledgeGraphRoutes
} from '../lib/knowledgeGraphRouteSearch';
import type { KnowledgeGraphModule } from '../types/projectKnowledgeGraph';

const { Text } = Typography;

type KnowledgeGraphRouteSearchProps = {
  variant?: 'panel' | 'toolbar';
  modules: KnowledgeGraphModule[];
  selectedModuleId: string | null;
  onSelectModule: (moduleId: string) => void;
};

export function KnowledgeGraphRouteSearch({
  variant = 'panel',
  modules,
  selectedModuleId,
  onSelectModule
}: KnowledgeGraphRouteSearchProps) {
  const [query, setQuery] = useState('');
  const routeCount = useMemo(
    () => modules.reduce((total, module) => total + (module.routes?.length ?? 0), 0),
    [modules]
  );
  const results = useMemo(
    () => searchKnowledgeGraphRoutes(modules, query),
    [modules, query]
  );
  const hasQuery = query.trim().length > 0;
  const isToolbar = variant === 'toolbar';

  return (
    <section
      className={isToolbar
        ? 'knowledge-route-search-panel knowledge-route-search-panel--toolbar'
        : 'knowledge-route-search-panel'}
      aria-label="相似接口搜索"
    >
      {isToolbar ? null : (
        <Flex align="center" justify="space-between" gap={12} className="knowledge-route-search-head">
          <Space size={8} wrap>
            <Route size={16} aria-hidden="true" />
            <Text className="field-label">相似接口搜索</Text>
            <Tag>{routeCount} 个接口</Tag>
          </Space>
          {hasQuery ? <Tag color={results.length ? 'blue' : 'default'}>{results.length} 个候选</Tag> : null}
        </Flex>
      )}
      <Input
        className="knowledge-route-search-input"
        allowClear
        prefix={<Search size={15} aria-hidden="true" />}
        placeholder="输入接口路径、方法、摘要、变量或 Body 字段"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      {hasQuery ? (
        results.length ? (
          <div className="knowledge-route-search-results">
            {results.map((result) => (
              <SearchResultRow
                key={`${result.module.id}-${result.route.id}`}
                result={result}
                active={result.module.id === selectedModuleId}
                onSelectModule={onSelectModule}
              />
            ))}
          </div>
        ) : (
          <Empty className="knowledge-route-search-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有相似接口" />
        )
      ) : null}
    </section>
  );
}

function SearchResultRow({
  result,
  active,
  onSelectModule
}: {
  result: KnowledgeGraphRouteSearchResult;
  active: boolean;
  onSelectModule: (moduleId: string) => void;
}) {
  return (
    <div className={active ? 'knowledge-route-search-row active' : 'knowledge-route-search-row'}>
      <Flex align="flex-start" justify="space-between" gap={10}>
        <div className="knowledge-route-search-copy">
          <Flex align="center" gap={8} wrap>
            <Text strong>{routeLabel(result.route)}</Text>
            <Tag color={scoreColor(result.score)}>{Math.min(result.score, 99)}%</Tag>
            {active ? <Tag color="blue">当前模块</Tag> : <Tag>{result.module.name}</Tag>}
          </Flex>
          {result.route.summary ? <Text className="analysis-path">{result.route.summary}</Text> : null}
          <Space size={6} wrap className="knowledge-route-search-reasons">
            {result.reasons.map((reason) => <Tag key={reason}>{reason}</Tag>)}
          </Space>
        </div>
        <Tooltip title="定位到模块">
          <Button
            className="icon-button"
            aria-label="定位到模块"
            icon={<LocateFixed size={15} />}
            onClick={() => onSelectModule(result.module.id)}
          />
        </Tooltip>
      </Flex>
    </div>
  );
}

function scoreColor(score: number): string {
  if (score >= 70) return 'green';
  if (score >= 40) return 'blue';
  return 'gold';
}
