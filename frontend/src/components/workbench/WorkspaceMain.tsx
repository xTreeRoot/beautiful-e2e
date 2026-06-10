import { Layout } from 'antd';
import type { MouseEvent as ReactMouseEvent, RefObject } from 'react';
import type { Connection, EdgeChange, NodeChange } from '@xyflow/react';

import type { Group, TestCase } from '../../api';
import type {
  CanvasEdge,
  CanvasNode,
  ContextToolbox,
  ExecutionMode,
  FlowPosition,
  NodeTemplate
} from '../../types/workbench';
import { FlowCanvas } from './FlowCanvas';
import { PromptBar } from './PromptBar';
import { WorkspaceTopbar } from './WorkspaceTopbar';

const { Content } = Layout;

type WorkspaceMainProps = {
  flowWrapperRef: RefObject<HTMLDivElement | null>;
  executionMode: ExecutionMode;
  activeGroup?: Group;
  selectedCase?: TestCase;
  status: string;
  offlineMode: boolean;
  isGenerating: boolean;
  isSaving: boolean;
  isRunningCase: boolean;
  hasCaseRunSnapshot: boolean;
  prompt: string;
  templates: NodeTemplate[];
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  contextToolbox: ContextToolbox | null;
  onPromptChange: (value: string) => void;
  onGenerate: () => void;
  onOpenAiConfig: () => void;
  onSaveCanvas: () => void;
  onRunCase: () => void;
  onOpenCaseRunSnapshot: () => void;
  onOpenDsl: () => void;
  onNodesChange: (changes: NodeChange<CanvasNode>[]) => void;
  onEdgesChange: (changes: EdgeChange<CanvasEdge>[]) => void;
  onConnect: (connection: Connection) => void;
  onPaneContextMenu: (event: globalThis.MouseEvent | ReactMouseEvent<Element, globalThis.MouseEvent>) => void;
  onCloseContextToolbox: () => void;
  onSelectedNodeChange: (nodeId: string) => void;
  onAddNode: (template: NodeTemplate, position?: FlowPosition) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitView: () => void;
};

export function WorkspaceMain({
  flowWrapperRef,
  executionMode,
  activeGroup,
  selectedCase,
  status,
  offlineMode,
  isGenerating,
  isSaving,
  isRunningCase,
  hasCaseRunSnapshot,
  prompt,
  templates,
  nodes,
  edges,
  contextToolbox,
  onPromptChange,
  onGenerate,
  onOpenAiConfig,
  onSaveCanvas,
  onRunCase,
  onOpenCaseRunSnapshot,
  onOpenDsl,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onPaneContextMenu,
  onCloseContextToolbox,
  onSelectedNodeChange,
  onAddNode,
  onZoomIn,
  onZoomOut,
  onFitView
}: WorkspaceMainProps) {
  return (
    <Layout className="workspace">
      <WorkspaceTopbar
        executionMode={executionMode}
        activeGroup={activeGroup}
        selectedCase={selectedCase}
        status={status}
        offlineMode={offlineMode}
        isGenerating={isGenerating}
        isSaving={isSaving}
        isRunningCase={isRunningCase}
        hasCaseRunSnapshot={hasCaseRunSnapshot}
        onGenerate={onGenerate}
        onOpenAiConfig={onOpenAiConfig}
        onSaveCanvas={onSaveCanvas}
        onRunCase={onRunCase}
        onOpenCaseRunSnapshot={onOpenCaseRunSnapshot}
        onOpenDsl={onOpenDsl}
      />

      <Content className="workspace-content">
        <section className="node-workbench">
          <div className="canvas-workspace-column">
            <PromptBar prompt={prompt} onPromptChange={onPromptChange} />

            <FlowCanvas
              flowWrapperRef={flowWrapperRef}
              selectedCase={selectedCase}
              nodes={nodes}
              edges={edges}
              contextToolbox={contextToolbox}
              templates={templates}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onPaneContextMenu={onPaneContextMenu}
              onCloseContextToolbox={onCloseContextToolbox}
              onSelectedNodeChange={onSelectedNodeChange}
              onAddNode={onAddNode}
              onZoomIn={onZoomIn}
              onZoomOut={onZoomOut}
              onFitView={onFitView}
            />
          </div>
        </section>
      </Content>
    </Layout>
  );
}
