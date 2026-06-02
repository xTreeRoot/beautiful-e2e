import { Sparkles } from 'lucide-react';

import type { GenerateProgressState } from '../../types/workbench';
import { StreamProgressModal } from './StreamProgressModal';

type GenerateProgressModalProps = {
  progress: GenerateProgressState;
  onConfirm: () => void;
};

export function GenerateProgressModal({ progress, onConfirm }: GenerateProgressModalProps) {
  return (
    <StreamProgressModal
      open={progress.open}
      runId={progress.runId}
      phase={progress.phase}
      lines={progress.lines}
      startedAt={progress.startedAt}
      finishedAt={progress.finishedAt}
      title="生成过程"
      titleIcon={<Sparkles size={18} aria-hidden="true" />}
      runningTitle="正在生成用例"
      completeTitle="生成已完成"
      errorTitle="生成遇到问题"
      runningDescription="当前请求会继续执行，下面会持续展示供应商 SSE 增量。"
      completeDescription="结果已写入工作台，5 秒后会自动确认。"
      errorDescription="错误信息已保留，确认后可以调整输入或稍后重试。"
      runningButtonLabel="生成中"
      emptyLine="建立流式生成连接..."
      onConfirm={onConfirm}
    />
  );
}
