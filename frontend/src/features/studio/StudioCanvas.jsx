import { useEffect, useRef, useState } from "react";
import { ReactFlow, Background, Controls, MiniMap, applyNodeChanges } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import "./StudioCanvas.css";

// The big AI Studio canvas, built on React Flow (https://reactflow.dev).
// You give it nodes (boxes) and edges (lines); React Flow handles pan, zoom, selecting and dragging.
//   nodes, edges  - { id, type, position, data } / { id, source, target }
//   nodeTypes     - our own box designs (features/studio/nodes)
//   edgeTypes     - our own line designs (features/studio/edges, e.g. the leafy vine)
//   onNodeClick   - (event, node) => ... when a box is clicked
//   onDropFile(f) - a file was dropped anywhere on the canvas
//   onNodeDragStop(event, node) - a box was dragged somewhere new (save node.position)
//
// Controls: scroll = pan, pinch or Ctrl/Cmd + scroll = zoom, hold Space + drag = pan (like Figma).
function StudioCanvas({ nodes, edges, nodeTypes, edgeTypes, onNodeClick, onDropFile, onNodeDragStop }) {
  // React Flow keeps its own copy of the boxes (where you dragged them, which is selected, their size).
  const [shownNodes, setShownNodes] = useState(nodes);
  const [lastNodes, setLastNodes] = useState(nodes);
  const flowRef = useRef(null);

  // New boxes from the page (e.g. clips just found): add them, but keep the boxes you already
  // moved where you left them. (Updating state while rendering is React's recommended way to
  // follow a prop: https://react.dev/learn/you-might-not-need-an-effect)
  if (nodes !== lastNodes) {
    setLastNodes(nodes);
    setShownNodes((current) => {
      const existing = new Map(current.map((node) => [node.id, node]));
      return nodes.map((node) => {
        const old = existing.get(node.id);
        return old ? { ...old, type: node.type, data: node.data } : node;
      });
    });
  }

  // When the number of boxes changes, zoom to show them all (after React Flow has measured them)
  useEffect(() => {
    const timer = setTimeout(() => flowRef.current?.fitView({ padding: 0.15, duration: 400 }), 50);
    return () => clearTimeout(timer);
  }, [nodes.length]);

  function handleDrop(event) {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file) onDropFile?.(file);
  }

  return (
    <div className="studio-canvas" onDragOver={(e) => e.preventDefault()} onDrop={handleDrop}>
      <ReactFlow
        nodes={shownNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={(changes) => setShownNodes((current) => applyNodeChanges(changes, current))}
        onNodeClick={onNodeClick}
        onNodeDragStop={onNodeDragStop}
        onInit={(instance) => (flowRef.current = instance)}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.2}
        maxZoom={1.5}
        panOnScroll
        nodesConnectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant="dots" gap={24} size={1.5} />
        <Controls position="bottom-right" showInteractive={false} />
        {/* React Flow's default minimap is 200 x 150; this one is smaller so it covers less canvas */}
        <MiniMap pannable zoomable position="bottom-left" style={{ width: 130, height: 90 }} />
      </ReactFlow>
    </div>
  );
}

export default StudioCanvas;
