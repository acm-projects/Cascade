import { useEffect, useMemo, useRef, useState } from "react";
import { createStudioWorld } from "./studioWorldScene";
import { ClipCard } from "../nodes/ClipNode";
import { SourceCard } from "../nodes/SourceNode";
import { sameRef } from "../graph";
import StudioCanvas from "../StudioCanvas";
import Icon from "../../../components/ui/Icon";
import "../nodes/nodes.css";
import "./StudioWorld.css";

// AI Studio's isometric world (studioWorldScene.js draws it): the same graph as the flat canvas
// (graph.js buildGraph), but as a little jungle island. The cards are the canvas's own cards, floating
// above their spot in the world and following it as you pan and zoom.
// If the device can't draw 3D, the flat React Flow canvas (StudioCanvas) is shown instead.
//   nodes, edges - from buildGraph   onDropFile(file) - a video was dropped on the world
//   (nodeTypes, edgeTypes, onNodeDragStop are passed through to the flat canvas fallback)

// The graph's boxes are laid out in screen pixels. In the world, left-to-right (the flow) is squeezed a bit
// and top-to-bottom (clips of the same prompt) is stretched, so stacked cards sit side by side on screen.
// These are the middle of each kind of box, from its top-left corner.
const CENTER = { source: [110, 95], generation: [65, 50], clip: [95, 130] };
const ACROSS = 0.85 / 100;   // world units per graph pixel, along the flow
const DOWN = 1.95 / 100;     // world units per graph pixel, down a stack of clips (enough that cards never overlap)
const CLIFF_ROOM = 5.2;      // the waterfall cliff is big: it sits this much further back

function toWorld(nodes, edges) {
  return {
    nodes: nodes.map((node) => {
      const [cx, cy] = CENTER[node.type] ?? [0, 0];
      const data = node.data;
      return {
        id: node.id,
        type: node.type,
        x: +((node.position.x + cx) * ACROSS - (node.type === "source" ? CLIFF_ROOM : 0)).toFixed(2),
        z: +((node.position.y + cy) * DOWN).toFixed(2),
        picked: node.type === "clip" && data.editorClips.some((item) => sameRef(item, data.ref)),
        busy: node.type === "generation" && ["queued", "processing"].includes(data.group.state),
      };
    }),
    edges: edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target, busy: Boolean(edge.animated) })),
  };
}

function StudioWorld({ nodes, edges, onDropFile, ...flatProps }) {
  const holderRef = useRef(null);
  const sceneRef = useRef(null);
  const cardRefs = useRef(new Map());
  const [failed, setFailed] = useState(false);

  // Start the 3D world once
  useEffect(() => {
    const holder = holderRef.current;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const canvas = document.createElement("canvas");
    canvas.className = "studio-world-canvas";
    holder.prepend(canvas);
    try {
      sceneRef.current = createStudioWorld(canvas, {
        still,
        // Every frame: move each card to its spot, sized to the zoom, nearer cards on top
        onFrame(places, pixelsPerUnit) {
          const scale = Math.min(1.1, Math.max(0.35, pixelsPerUnit / 80));
          for (const [id, element] of cardRefs.current) {
            const place = places[id];
            if (!element || !place) continue;
            element.style.transform = `translate(${place.x.toFixed(1)}px, ${place.y.toFixed(1)}px) translate(-50%, -100%) scale(${scale.toFixed(3)})`;
            element.style.zIndex = String(Math.round(place.y));
            element.style.opacity = String(place.fade ?? 1);   // new cards fade in as their land rises
          }
        },
      });
    } catch {
      canvas.remove();
      setFailed(true);   // eslint-disable-line react-hooks/set-state-in-effect -- one-time fallback
    }
    return () => {
      sceneRef.current?.stop();
      sceneRef.current = null;
      canvas.remove();
    };
  }, []);

  const worldGraph = useMemo(() => toWorld(nodes, edges), [nodes, edges]);
  useEffect(() => {
    sceneRef.current?.setGraph(worldGraph);
  }, [worldGraph]);

  if (failed) return <StudioCanvas nodes={nodes} edges={edges} onDropFile={onDropFile} {...flatProps} />;

  function handleDrop(event) {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file) onDropFile?.(file);
  }

  const keep = (id) => (element) => {
    if (element) cardRefs.current.set(id, element);
    else cardRefs.current.delete(id);
  };

  return (
    <div ref={holderRef} className="studio-world" onDragOver={(e) => e.preventDefault()} onDrop={handleDrop}>
      <div className="studio-world-cards">
        {nodes.map((node) => (
          <div key={node.id} ref={keep(node.id)} className={`studio-world-card is-${node.type}`}>
            {node.type === "source" && <SourceCard data={node.data} />}
            {node.type === "clip" && <ClipCard data={node.data} />}
            {node.type === "generation" && <PadLabel data={node.data} />}
          </div>
        ))}
      </div>
      <div className="studio-world-controls" role="group" aria-label="Map view">
        <button type="button" onClick={() => sceneRef.current?.zoomBy(1.25)} aria-label="Zoom in"><Icon name="plus" /></button>
        <button type="button" onClick={() => sceneRef.current?.zoomBy(0.8)} aria-label="Zoom out"><span aria-hidden="true">−</span></button>
        <button type="button" onClick={() => sceneRef.current?.fit()} aria-label="Reset the view"><Icon name="grid" /></button>
      </div>
      <p className="studio-world-hint">Drag to turn · right-drag or Shift + drag to move · pinch or Ctrl + scroll to zoom</p>
    </div>
  );
}

// The little sign on a prompt's lily pad: P1, P2... Click it to jump to that prompt in the chat.
function PadLabel({ data }) {
  const { group, number, onFocusPrompt, referenceLabels = [] } = data;
  const context = referenceLabels.length > 1 ? `Combines ${referenceLabels.map((ref) => `Clip ${ref.label}`).join(" + ")}. ` : "";
  return (
    <button type="button" className={`studio-world-pad is-${group.state}`} onClick={() => onFocusPrompt?.(group.job_id)}
      title={`${context}${group.prompt}\nOpen this prompt in AI chat`} aria-label={`Go to prompt ${number} in AI chat: ${group.prompt}`}>
      P{number}
    </button>
  );
}

export default StudioWorld;
