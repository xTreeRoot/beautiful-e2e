import { Button, Flex, Progress, Space, Tag, Typography } from 'antd';
import { FileText, RefreshCw, WandSparkles } from 'lucide-react';
import { useEffect, useState, type SyntheticEvent } from 'react';

import type { DomModuleCompileMode } from '../api';
import type { DomCompileProgressState, DomFileGroup } from '../lib/domTargetGraph';

const { Text } = Typography;

type DomPagePreviewCardProps = {
  module: DomFileGroup;
  compileProgress?: DomCompileProgressState | null;
  onCompile?: (mode: DomModuleCompileMode) => void;
};

export function DomPagePreviewCard({
  module,
  compileProgress,
  onCompile
}: DomPagePreviewCardProps) {
  const previewHtml = module.previewHtml?.trim() ?? '';
  const previewSource = module.previewSource ?? module.source;
  const previewLabel = previewLabelForStrategy(module.previewStrategy, module.isCompiled);
  const activeProgress = compileProgress?.moduleId === module.id ? compileProgress : null;
  const isCompiling = activeProgress?.phase === 'running';
  const [frameHeight, setFrameHeight] = useState(320);
  useEffect(() => {
    setFrameHeight(320);
  }, [previewHtml, module.id]);
  const handlePreviewFrameLoad = (event: SyntheticEvent<HTMLIFrameElement>) => {
    let frameDocument: Document | null = null;
    try {
      frameDocument = event.currentTarget.contentDocument;
    } catch {
      return;
    }
    if (!frameDocument) return;
    const bodyHeight = frameDocument.body?.scrollHeight ?? 0;
    const bodyOffsetHeight = frameDocument.body?.offsetHeight ?? 0;
    const documentHeight = frameDocument.documentElement?.scrollHeight ?? 0;
    const documentOffsetHeight = frameDocument.documentElement?.offsetHeight ?? 0;
    const nextHeight = Math.max(bodyHeight, bodyOffsetHeight, documentHeight, documentOffsetHeight);
    if (nextHeight > 0) {
      setFrameHeight(Math.max(220, Math.ceil(nextHeight) + 2));
    }
  };
  return (
    <div className="dom-page-preview-card">
      <Flex align="center" justify="space-between" gap={8} className="dom-page-preview-head">
        <Space size={8}>
          <FileText size={15} aria-hidden="true" />
          <Text strong>系统内渲染预览</Text>
        </Space>
        <Space size={6}>
          {previewHtml ? <Tag>{previewLabel}</Tag> : <Tag>等待预览</Tag>}
          {module.isCompiled ? <Tag color="success">已完成编译</Tag> : <Tag>未编译</Tag>}
        </Space>
      </Flex>
      {onCompile ? (
        <Flex align="center" justify="space-between" gap={8} className="dom-page-preview-actions">
          <Space size={6} wrap>
            <Button
              size="small"
              icon={<RefreshCw size={14} />}
              disabled={isCompiling}
              loading={isCompiling && activeProgress?.mode === 'static'}
              onClick={() => onCompile('static')}
            >
              静态编译
            </Button>
            <Button
              size="small"
              icon={<WandSparkles size={14} />}
              disabled={isCompiling}
              loading={isCompiling && activeProgress?.mode === 'ai'}
              onClick={() => onCompile('ai')}
            >
              AI 修复编译
            </Button>
          </Space>
        </Flex>
      ) : null}
      {activeProgress ? (
        <div className="dom-page-preview-progress">
          <Progress
            percent={activeProgress.percent}
            size="small"
            status={activeProgress.phase === 'error' ? 'exception' : activeProgress.phase === 'complete' ? 'success' : 'active'}
          />
          <Text className="analysis-path">{activeProgress.message}</Text>
        </div>
      ) : null}
      {previewHtml ? (
        <>
          <Text className="analysis-source">
            {module.framework ? `${module.framework} · ` : ''}{previewSource}
          </Text>
          <iframe
            className="dom-page-preview-frame"
            title={`系统内预览：${module.moduleName}`}
            srcDoc={previewHtml}
            loading="lazy"
            // 只放开同源读取用于测量 srcDoc 高度，脚本执行仍由 sandbox 拦截。
            sandbox="allow-same-origin"
            scrolling="no"
            style={{ height: frameHeight }}
            onLoad={handlePreviewFrameLoad}
          />
        </>
      ) : (
        <Text className="analysis-path">
          当前模块还没有系统内编译结果，可使用 DOM 页面编译/修复 AI 用途补全页面草图。
        </Text>
      )}
    </div>
  );
}

function previewLabelForStrategy(strategy: string | null, isCompiled: boolean): string {
  if (strategy === 'ai_dom_compilation') return 'AI 修复编译';
  if (strategy === 'static_dom_sketch') return isCompiled ? '静态编译' : '静态草图';
  return '已编译';
}
