import { useState } from 'react';

import type { GenerateCaseStreamEvent } from '../api';
import type { ExecutionMode, GenerateProgressState } from '../types/workbench';

type StartGenerateProgressOptions = {
  runId: number;
  prompt: string;
  executionMode: ExecutionMode;
  initialLine?: string;
};

const INITIAL_GENERATE_PROGRESS: GenerateProgressState = {
  open: false,
  runId: 0,
  phase: 'idle',
  prompt: '',
  executionMode: 'fullstack',
  detail: '',
  lines: [],
  startedAt: null,
  finishedAt: null
};

/**
 * 管理 AI 生成弹窗的流式状态。
 * 供应商 SSE 的 reasoning/content 增量只影响生成进度面板，放在独立 hook 中避免污染工作台项目、画布和用例编排逻辑。
 */
export function useGenerateProgress() {
  const [isGenerating, setIsGenerating] = useState(false);
  const [generateProgress, setGenerateProgress] = useState<GenerateProgressState>(
    INITIAL_GENERATE_PROGRESS
  );

  function startGenerateProgress({
    runId,
    prompt,
    executionMode,
    initialLine = '建立流式生成连接...'
  }: StartGenerateProgressOptions) {
    setGenerateProgress({
      open: true,
      runId,
      phase: 'running',
      prompt,
      executionMode,
      detail: '',
      lines: [initialLine],
      startedAt: Date.now(),
      finishedAt: null
    });
    setIsGenerating(true);
  }

  function closeGenerateProgress() {
    setGenerateProgress((current) => ({ ...current, open: false }));
  }

  function appendGenerateProgressLine(runId: number, message: string) {
    const normalized = message.trim();
    if (!normalized) return;
    setGenerateProgress((current) => {
      if (current.runId !== runId) return current;
      if (current.lines[current.lines.length - 1] === normalized) return current;
      return { ...current, lines: [...current.lines, normalized] };
    });
  }

  function appendGenerateProgressDelta(runId: number, event: GenerateCaseStreamEvent) {
    const delta = typeof event.delta === 'string' ? event.delta : '';
    if (!delta) return;
    const channel = event.channel === 'reasoning' ? 'reasoning' : 'content';
    const prefix = channel === 'reasoning' ? '供应商思考：' : '供应商输出：';
    setGenerateProgress((current) => {
      if (current.runId !== runId) return current;
      const lines = [...current.lines];
      const parts = delta.split(/\r?\n/);

      for (const [index, part] of parts.entries()) {
        if (!part && index === parts.length - 1) continue;
        const lastIndex = lines.length - 1;
        if (lastIndex >= 0 && lines[lastIndex].startsWith(prefix)) {
          lines[lastIndex] = `${lines[lastIndex]}${part}`;
        } else {
          lines.push(`${prefix}${part}`);
        }
        if (index < parts.length - 1) lines.push(prefix);
      }

      return { ...current, lines };
    });
  }

  function finishGenerateProgress(
    runId: number,
    phase: Extract<GenerateProgressState['phase'], 'complete' | 'error'>,
    detail: string
  ) {
    setGenerateProgress((current) => {
      if (current.runId !== runId) return current;
      const lines =
        detail && current.lines[current.lines.length - 1] !== detail
          ? [...current.lines, detail]
          : current.lines;
      return { ...current, phase, detail, lines, finishedAt: Date.now() };
    });
  }

  return {
    isGenerating,
    setIsGenerating,
    generateProgress,
    startGenerateProgress,
    closeGenerateProgress,
    appendGenerateProgressLine,
    appendGenerateProgressDelta,
    finishGenerateProgress
  };
}
