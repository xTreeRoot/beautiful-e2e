import { useState } from 'react';

import type { ProjectAnalysisStreamEvent } from '../api';
import type { ProjectAnalysisProgressState } from '../types/workbench';

type StartProjectAnalysisProgressOptions = {
  runId: number;
  projectName: string;
  initialLine?: string;
};

const INITIAL_PROJECT_ANALYSIS_PROGRESS: ProjectAnalysisProgressState = {
  open: false,
  runId: 0,
  phase: 'idle',
  projectName: '',
  detail: '',
  lines: [],
  startedAt: null,
  finishedAt: null
};

/**
 * 管理项目分析 SSE 弹窗状态。
 * 分析进度只和项目索引刷新有关，独立 hook 可以避免把扫描细节塞回工作台总控制器。
 */
export function useProjectAnalysisProgress() {
  const [projectAnalysisProgress, setProjectAnalysisProgress] =
    useState<ProjectAnalysisProgressState>(INITIAL_PROJECT_ANALYSIS_PROGRESS);

  function startProjectAnalysisProgress({
    runId,
    projectName,
    initialLine = '建立项目分析流式连接...'
  }: StartProjectAnalysisProgressOptions) {
    setProjectAnalysisProgress({
      open: true,
      runId,
      phase: 'running',
      projectName,
      detail: '',
      lines: [initialLine],
      startedAt: Date.now(),
      finishedAt: null
    });
  }

  function closeProjectAnalysisProgress() {
    setProjectAnalysisProgress((current) => ({ ...current, open: false }));
  }

  function appendProjectAnalysisProgressLine(runId: number, message: string) {
    const normalized = message.trim();
    if (!normalized) return;
    setProjectAnalysisProgress((current) => {
      if (current.runId !== runId) return current;
      if (current.lines[current.lines.length - 1] === normalized) return current;
      return { ...current, lines: [...current.lines, normalized] };
    });
  }

  function applyProjectAnalysisProgressEvent(runId: number, event: ProjectAnalysisStreamEvent) {
    if (typeof event.message === 'string') {
      appendProjectAnalysisProgressLine(runId, event.message);
    }
  }

  function finishProjectAnalysisProgress(
    runId: number,
    phase: Extract<ProjectAnalysisProgressState['phase'], 'complete' | 'error'>,
    detail: string
  ) {
    setProjectAnalysisProgress((current) => {
      if (current.runId !== runId) return current;
      const lines =
        detail && current.lines[current.lines.length - 1] !== detail
          ? [...current.lines, detail]
          : current.lines;
      return { ...current, phase, detail, lines, finishedAt: Date.now() };
    });
  }

  return {
    projectAnalysisProgress,
    startProjectAnalysisProgress,
    closeProjectAnalysisProgress,
    applyProjectAnalysisProgressEvent,
    finishProjectAnalysisProgress
  };
}
