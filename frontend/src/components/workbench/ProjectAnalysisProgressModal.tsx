import { Network } from 'lucide-react';

import type { ProjectAnalysisProgressState } from '../../types/workbench';
import { StreamProgressModal } from './StreamProgressModal';

type ProjectAnalysisProgressModalProps = {
  progress: ProjectAnalysisProgressState;
  onConfirm: () => void;
};

export function ProjectAnalysisProgressModal({
  progress,
  onConfirm
}: ProjectAnalysisProgressModalProps) {
  return (
    <StreamProgressModal
      open={progress.open}
      runId={progress.runId}
      phase={progress.phase}
      lines={progress.lines}
      startedAt={progress.startedAt}
      finishedAt={progress.finishedAt}
      title="分析过程"
      titleIcon={<Network size={18} aria-hidden="true" />}
      runningTitle="正在分析项目"
      completeTitle="分析已完成"
      errorTitle="分析遇到问题"
      runningDescription="当前请求会继续执行，下面会持续展示仓库扫描和索引写入进度。"
      completeDescription="项目索引已刷新，5 秒后会自动确认。"
      errorDescription="错误信息已保留，确认后可以检查路径或稍后重试。"
      runningButtonLabel="分析中"
      emptyLine="建立项目分析流式连接..."
      onConfirm={onConfirm}
    />
  );
}
