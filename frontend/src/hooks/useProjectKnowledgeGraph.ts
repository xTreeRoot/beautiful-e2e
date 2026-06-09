import { useCallback, useEffect, useState } from 'react';

import { api, type Project } from '../api';
import type { ProjectKnowledgeGraph } from '../types/projectKnowledgeGraph';

type ToastType = 'success' | 'info' | 'warning' | 'error';

type UseProjectKnowledgeGraphOptions = {
  open: boolean;
  project?: Project;
  showToast?: (type: ToastType, content: string) => void;
};

/**
 * 管理项目知识图谱的加载和审核动作。
 * 图谱审核属于项目分析中心局部状态，不进入工作台全局 controller，避免扩大主控制器职责。
 */
export function useProjectKnowledgeGraph({
  open,
  project,
  showToast
}: UseProjectKnowledgeGraphOptions) {
  const [knowledgeGraph, setKnowledgeGraph] = useState<ProjectKnowledgeGraph | null>(null);
  const [isLoadingKnowledgeGraph, setIsLoadingKnowledgeGraph] = useState(false);
  const [isSavingKnowledgeGraph, setIsSavingKnowledgeGraph] = useState(false);
  const [knowledgeGraphError, setKnowledgeGraphError] = useState<string | null>(null);

  const loadKnowledgeGraph = useCallback(async () => {
    if (!project) {
      setKnowledgeGraph(null);
      setKnowledgeGraphError(null);
      return;
    }
    setIsLoadingKnowledgeGraph(true);
    setKnowledgeGraphError(null);
    try {
      const graph = await api.getProjectKnowledgeGraph(project.id);
      setKnowledgeGraph(graph);
    } catch (error) {
      setKnowledgeGraph(null);
      const message = error instanceof Error && error.message.includes('404')
        ? '项目知识图谱尚未生成'
        : '项目知识图谱加载失败';
      setKnowledgeGraphError(message);
    } finally {
      setIsLoadingKnowledgeGraph(false);
    }
  }, [project]);

  useEffect(() => {
    if (!open) return;
    void loadKnowledgeGraph();
  }, [open, loadKnowledgeGraph]);

  const rebuildKnowledgeGraph = useCallback(async () => {
    if (!project) return;
    setIsSavingKnowledgeGraph(true);
    setKnowledgeGraphError(null);
    try {
      const graph = await api.rebuildProjectKnowledgeGraph(project.id);
      setKnowledgeGraph(graph);
      showToast?.('success', '知识图谱候选已重建');
    } catch (error) {
      const message = error instanceof Error ? error.message : '知识图谱重建失败';
      setKnowledgeGraphError(message);
      showToast?.('error', message);
    } finally {
      setIsSavingKnowledgeGraph(false);
    }
  }, [project, showToast]);

  const saveKnowledgeGraph = useCallback(async (
    nextGraph: ProjectKnowledgeGraph['graph'],
    reviewStatus?: string,
    reviewNotes?: string | null
  ) => {
    if (!project) return;
    setIsSavingKnowledgeGraph(true);
    setKnowledgeGraphError(null);
    try {
      const saved = await api.updateProjectKnowledgeGraph(project.id, {
        graph: nextGraph,
        review_status: reviewStatus ?? knowledgeGraph?.review_status ?? 'draft',
        review_notes: reviewNotes ?? knowledgeGraph?.review_notes,
        actor: 'developer'
      });
      setKnowledgeGraph(saved);
      showToast?.('success', '知识图谱校正已保存');
    } catch (error) {
      const message = error instanceof Error ? error.message : '知识图谱校正保存失败';
      setKnowledgeGraphError(message);
      showToast?.('error', message);
    } finally {
      setIsSavingKnowledgeGraph(false);
    }
  }, [knowledgeGraph?.review_notes, knowledgeGraph?.review_status, project, showToast]);

  const approveKnowledgeGraph = useCallback(async () => {
    if (!project || !knowledgeGraph) return;
    setIsSavingKnowledgeGraph(true);
    setKnowledgeGraphError(null);
    try {
      const saved = await api.updateProjectKnowledgeGraph(project.id, {
        graph: knowledgeGraph.graph,
        review_status: 'reviewed',
        review_notes: knowledgeGraph.review_notes,
        actor: 'developer'
      });
      setKnowledgeGraph(saved);
      showToast?.('success', '知识图谱已批准为生成强事实');
    } catch (error) {
      const message = error instanceof Error ? error.message : '知识图谱审核保存失败';
      setKnowledgeGraphError(message);
      showToast?.('error', message);
    } finally {
      setIsSavingKnowledgeGraph(false);
    }
  }, [knowledgeGraph, project, showToast]);

  return {
    knowledgeGraph,
    isLoadingKnowledgeGraph,
    isSavingKnowledgeGraph,
    knowledgeGraphError,
    loadKnowledgeGraph,
    rebuildKnowledgeGraph,
    saveKnowledgeGraph,
    approveKnowledgeGraph
  };
}
