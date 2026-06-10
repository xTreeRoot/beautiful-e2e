import { Button, Space, Tag, Tooltip } from 'antd';
import { GitBranch, RefreshCw, ShieldCheck } from 'lucide-react';

import type { KnowledgeGraphModule } from '../types/projectKnowledgeGraph';
import { KnowledgeGraphRouteSearch } from './KnowledgeGraphRouteSearch';

type ProjectKnowledgeGraphToolbarProps = {
  modules: KnowledgeGraphModule[];
  relationshipCount: number;
  isReviewed: boolean;
  saving: boolean;
  selectedModuleId: string | null;
  onSelectModule: (moduleId: string) => void;
  onReload: () => void;
  onRebuild: () => void;
  onApprove: () => void;
};

/**
 * 图谱顶部工具栏只承载全局状态、接口搜索和图谱级操作。
 * 搜索结果仍由搜索组件自己管理，避免把局部输入状态塞回图谱主面板。
 */
export function ProjectKnowledgeGraphToolbar({
  modules,
  relationshipCount,
  isReviewed,
  saving,
  selectedModuleId,
  onSelectModule,
  onReload,
  onRebuild,
  onApprove
}: ProjectKnowledgeGraphToolbarProps) {
  return (
    <div className="knowledge-graph-toolbar">
      <Space size={8} wrap className="knowledge-graph-status">
        <Tag color={isReviewed ? 'green' : 'gold'}>{isReviewed ? '已审核强事实' : '候选事实'}</Tag>
        <Tag>{modules.length} 个模块</Tag>
        <Tag>{relationshipCount} 条关系</Tag>
      </Space>

      <KnowledgeGraphRouteSearch
        variant="toolbar"
        modules={modules}
        selectedModuleId={selectedModuleId}
        onSelectModule={onSelectModule}
      />

      <Space size={8} wrap className="knowledge-graph-actions">
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
    </div>
  );
}
