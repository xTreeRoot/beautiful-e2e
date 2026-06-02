import type { RefObject, MouseEvent as ReactMouseEvent } from 'react';
import { Button, Card, Space, Tooltip } from 'antd';
import { Background, MiniMap, ReactFlow, type Connection, type EdgeChange, type NodeChange } from '@xyflow/react';
import { Maximize2, ZoomIn, ZoomOut } from 'lucide-react';

import type { TestCase } from '../../api';
import type { CanvasEdge, CanvasNode, ContextToolbox, FlowPosition, NodeTemplate } from '../../types/workbench';
import { NodeToolbox } from '../NodeToolbox';

type FlowCanvasProps = {
  flowWrapperRef: RefObject<HTMLDivElement | null>;
  selectedCase?: TestCase;
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  contextToolbox: ContextToolbox | null;
  templates: NodeTemplate[];
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

export function FlowCanvas({
  flowWrapperRef,
  selectedCase,
  nodes,
  edges,
  contextToolbox,
  templates,
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
}: FlowCanvasProps) {
  return (
    <div className="flow-zone" ref={flowWrapperRef}>
      {contextToolbox ? (
        <Card
          className="node-toolbox context-toolbox"
          size="small"
          style={{ left: contextToolbox.x, top: contextToolbox.y }}
          aria-label="上下文节点工具箱"
          onMouseDown={(event) => event.stopPropagation()}
          onClick={(event) => event.stopPropagation()}
          onContextMenu={(event) => event.preventDefault()}
        >
          <NodeToolbox templates={templates} onSelect={(template) => onAddNode(template, contextToolbox.flowPosition)} />
        </Card>
      ) : null}
      <ReactFlow
        key={selectedCase?.id ?? 'empty-graph'}
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onPaneClick={onCloseContextToolbox}
        onPaneContextMenu={onPaneContextMenu}
        onMoveStart={onCloseContextToolbox}
        onNodeClick={(_, node) => {
          onCloseContextToolbox();
          onSelectedNodeChange(node.id);
        }}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        nodesDraggable
        nodesConnectable
        elementsSelectable
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <MiniMap pannable zoomable />
      </ReactFlow>
      <Space.Compact
        direction="vertical"
        className="canvas-controls"
        onMouseDown={(event) => event.stopPropagation()}
        onClick={(event) => event.stopPropagation()}
      >
        <Tooltip title="放大" placement="right">
          <Button aria-label="放大" icon={<ZoomIn size={16} />} onClick={onZoomIn} />
        </Tooltip>
        <Tooltip title="缩小" placement="right">
          <Button aria-label="缩小" icon={<ZoomOut size={16} />} onClick={onZoomOut} />
        </Tooltip>
        <Tooltip title="适配视图" placement="right">
          <Button aria-label="适配视图" icon={<Maximize2 size={16} />} onClick={onFitView} />
        </Tooltip>
      </Space.Compact>
    </div>
  );
}
