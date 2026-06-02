import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent
} from 'react';
import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type EdgeChange,
  type NodeChange,
  useReactFlow
} from '@xyflow/react';

import type { TestCase } from '../api';
import { clamp, makeNodeData, toCanvasEdges, toCanvasNodes } from '../lib/canvas';
import { executableKinds } from '../lib/workbenchConstants';
import type {
  CanvasEdge,
  CanvasNode,
  CanvasNodeData,
  ContextToolbox,
  ExecutionMode,
  FlowPosition,
  NodeTemplate
} from '../types/workbench';

type UseWorkbenchCanvasOptions = {
  executionMode: ExecutionMode;
  updatePrompt: (value: string) => void;
  setIsNodeEditorOpen: (open: boolean) => void;
};

/**
 * 管理 React Flow 画布状态和画布交互。
 * 画布节点、边、选中节点和右键工具箱是同一组 UI 状态，独立成 hook 后总控制器只需要关心保存和生成时读取 DSL。
 */
export function useWorkbenchCanvas({
  executionMode,
  updatePrompt,
  setIsNodeEditorOpen
}: UseWorkbenchCanvasOptions) {
  const flowWrapperRef = useRef<HTMLDivElement | null>(null);
  const { fitView, screenToFlowPosition, zoomIn, zoomOut } = useReactFlow();
  const [nodes, setNodes] = useState<CanvasNode[]>([]);
  const [edges, setEdges] = useState<CanvasEdge[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [contextToolbox, setContextToolbox] = useState<ContextToolbox | null>(null);

  function applyCaseToCanvas(nextCase: TestCase | undefined) {
    if (!nextCase) {
      setNodes([]);
      setEdges([]);
      updatePrompt('');
      setSelectedNodeId(null);
      setContextToolbox(null);
      setIsNodeEditorOpen(false);
      return;
    }

    updatePrompt(nextCase.source_prompt ?? '');
    const nextNodes = toCanvasNodes(nextCase);
    setNodes(nextNodes);
    setEdges(toCanvasEdges(nextCase.graph));
    setSelectedNodeId(nextNodes.find((node) => executableKinds.has(node.data.kind))?.id ?? null);
    setContextToolbox(null);
    setIsNodeEditorOpen(false);
  }

  useEffect(() => {
    setContextToolbox(null);
  }, [executionMode]);

  useEffect(() => {
    if (!contextToolbox) return undefined;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setContextToolbox(null);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [contextToolbox]);

  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? null;

  const onNodesChange = useCallback((changes: NodeChange<CanvasNode>[]) => {
    setNodes((current) => applyNodeChanges(changes, current));
  }, []);

  const onEdgesChange = useCallback((changes: EdgeChange<CanvasEdge>[]) => {
    setEdges((current) => applyEdgeChanges(changes, current));
  }, []);

  const onConnect = useCallback((connection: Connection) => {
    setEdges((current) => addEdge({ ...connection, type: 'smoothstep' }, current));
  }, []);

  const onPaneContextMenu = useCallback(
    (event: globalThis.MouseEvent | ReactMouseEvent<Element, globalThis.MouseEvent>) => {
      event.preventDefault();
      const rect = flowWrapperRef.current?.getBoundingClientRect();
      if (!rect) return;
      const menuWidth = 220;
      const menuHeight = 190;
      const localX = event.clientX - rect.left;
      const localY = event.clientY - rect.top;
      setContextToolbox({
        x: clamp(localX, 8, Math.max(8, rect.width - menuWidth - 8)),
        y: clamp(localY, 8, Math.max(8, rect.height - menuHeight - 8)),
        flowPosition: screenToFlowPosition({ x: event.clientX, y: event.clientY })
      });
    },
    [screenToFlowPosition]
  );

  function addNodeFromTemplate(template: NodeTemplate, position?: FlowPosition) {
    const id = `${template.kind}-${Date.now()}`;
    const data = makeNodeData(template, executionMode);
    const nextNode: CanvasNode = {
      id,
      type: 'default',
      data,
      position: position ?? { x: 260 + (nodes.length % 4) * 180, y: 120 + Math.floor(nodes.length / 4) * 110 }
    };
    setNodes((current) => [...current, nextNode]);
    setSelectedNodeId(id);
    setIsNodeEditorOpen(true);
    setContextToolbox(null);
  }

  function updateSelectedNode(patch: Partial<CanvasNodeData>) {
    if (!selectedNodeId) return;
    setNodes((current) =>
      current.map((node) =>
        node.id === selectedNodeId ? { ...node, data: { ...node.data, ...patch } } : node
      )
    );
  }

  function deleteSelectedNode() {
    if (!selectedNodeId) return;
    setNodes((current) => current.filter((node) => node.id !== selectedNodeId));
    setEdges((current) =>
      current.filter((edge) => edge.source !== selectedNodeId && edge.target !== selectedNodeId)
    );
    setSelectedNodeId(null);
    setIsNodeEditorOpen(false);
  }

  return {
    flowWrapperRef,
    fitView,
    zoomIn,
    zoomOut,
    nodes,
    edges,
    selectedNode,
    selectedNodeId,
    setSelectedNodeId,
    contextToolbox,
    setContextToolbox,
    applyCaseToCanvas,
    onNodesChange,
    onEdgesChange,
    onConnect,
    onPaneContextMenu,
    addNodeFromTemplate,
    updateSelectedNode,
    deleteSelectedNode
  };
}
