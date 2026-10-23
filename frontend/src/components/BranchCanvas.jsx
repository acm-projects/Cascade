import { useEffect, useRef, useState } from "react";
import "./BranchCanvas.css";
import { SOURCE_SIZE, CLIP_SIZE } from "../utils/canvasLayout";

const MIN_ZOOM = 0.25;
const MAX_ZOOM = 2.5;
const tools = [
  { id: "select", label: "Select", icon: "➚" },
  { id: "pan", label: "Pan", icon: "✋" },
  { id: "zoom", label: "Zoom", icon: "🔍" },
];

// A Figma-style canvas: pan, zoom, and drag nodes. The video sits on the left and
// each clip is connected to it with a vine.
//   sourcePos / onMoveSource(pos)  - where the video node is, and moving it
//   renderSource()                 - what goes inside the video node
//   clips / onMoveClip(id, pos)    - clip nodes ({ id, x, y }) and moving them
//   renderClip(clip)               - what goes inside each clip node
//   ghosts                         - [{ x, y }] placeholder nodes while clips are generating
//   onDropFile(file)               - a file was dropped anywhere on the canvas
//   onArrange()                    - the Arrange button
//   extra                          - more buttons for the top-right of the toolbar
function BranchCanvas({
  sourcePos, onMoveSource, renderSource, clips, onMoveClip, renderClip,
  ghosts = [], onDropFile, onArrange, extra,
}) {
  const viewportRef = useRef(null);
  const [view, setView] = useState({ x: 30, y: 10, zoom: 0.85 });   // pan offset + zoom level
  const [tool, setTool] = useState("select");
  const [spaceHeld, setSpaceHeld] = useState(false);
  const [isPanning, setIsPanning] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const drag = useRef(null);          // what's being dragged right now
  const justDragged = useRef(false);  // true right after a drag, so it doesn't count as a click
  const viewRef = useRef(view);
  viewRef.current = view;

  // Zoom in/out around a point on the screen, so that point stays under the cursor
  function zoomAt(factor, px, py) {
    setView((v) => {
      const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, v.zoom * factor));
      const k = zoom / v.zoom;
      return { zoom, x: px - (px - v.x) * k, y: py - (py - v.y) * k };
    });
  }

  function zoomAtCenter(factor) {
    const rect = viewportRef.current.getBoundingClientRect();
    zoomAt(factor, rect.width / 2, rect.height / 2);
  }

  // Zoom and pan so every node fits on screen
  function fitToView() {
    const rect = viewportRef.current.getBoundingClientRect();
    const boxes = [
      { x: sourcePos.x, y: sourcePos.y, w: SOURCE_SIZE.w, h: SOURCE_SIZE.h },
      ...[...clips, ...ghosts].map((c) => ({ x: c.x, y: c.y, w: CLIP_SIZE.w, h: CLIP_SIZE.h })),
    ];
    const left = Math.min(...boxes.map((b) => b.x));
    const top = Math.min(...boxes.map((b) => b.y));
    const right = Math.max(...boxes.map((b) => b.x + b.w));
    const bottom = Math.max(...boxes.map((b) => b.y + b.h));
    const pad = 70;
    const zoom = Math.min(1.2, Math.max(MIN_ZOOM,
      Math.min((rect.width - pad * 2) / (right - left), (rect.height - pad * 2 - 60) / (bottom - top))));
    setView({
      zoom,
      x: (rect.width - (right - left) * zoom) / 2 - left * zoom,
      y: (rect.height + 50 - (bottom - top) * zoom) / 2 - top * zoom,
    });
  }

  // When new clips or placeholders appear, zoom out to show them all
  const nodeCount = clips.length + ghosts.length;
  useEffect(() => {
    if (nodeCount > 0) fitToView();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeCount]);

  // Trackpad / mouse wheel: scroll = pan, pinch or Ctrl/Cmd + scroll = zoom
  useEffect(() => {
    const el = viewportRef.current;
    function onWheel(e) {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      if (e.ctrlKey || e.metaKey) {
        zoomAt(Math.exp(-e.deltaY * 0.01), e.clientX - rect.left, e.clientY - rect.top);
      } else {
        setView((v) => ({ ...v, x: v.x - e.deltaX, y: v.y - e.deltaY }));
      }
    }
    el.addEventListener("wheel", onWheel, { passive: false });   // passive: false lets us stop the page scrolling
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  // Hold Space to pan with any tool (like Figma)
  useEffect(() => {
    function isTyping(e) {
      return ["INPUT", "TEXTAREA"].includes(e.target.tagName);
    }
    function down(e) {
      if (e.code === "Space" && !isTyping(e)) { e.preventDefault(); setSpaceHeld(true); }
    }
    function up(e) {
      if (e.code === "Space") setSpaceHeld(false);
    }
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => { window.removeEventListener("keydown", down); window.removeEventListener("keyup", up); };
  }, []);

  // Moving the mouse while something is held: pan the view, or move a node
  useEffect(() => {
    function onMove(e) {
      const d = drag.current;
      if (!d) return;
      const dx = e.clientX - d.startX;
      const dy = e.clientY - d.startY;
      if (Math.abs(dx) + Math.abs(dy) > 4) d.moved = true;
      if (d.kind === "pan") {
        setView((v) => ({ ...v, x: d.orig.x + dx, y: d.orig.y + dy }));
      } else {
        const zoom = viewRef.current.zoom;
        d.move({ x: d.orig.x + dx / zoom, y: d.orig.y + dy / zoom });
      }
    }
    function onUp() {
      if (!drag.current) return;
      justDragged.current = drag.current.moved;
      drag.current = null;
      setIsPanning(false);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => { window.removeEventListener("pointermove", onMove); window.removeEventListener("pointerup", onUp); };
  }, []);

  // Pressing on empty canvas
  function handleCanvasDown(e) {
    if (e.button !== 0 && e.button !== 1) return;
    const rect = viewportRef.current.getBoundingClientRect();
    if (tool === "zoom" && !spaceHeld && e.button === 0) {
      zoomAt(e.altKey || e.shiftKey ? 0.8 : 1.25, e.clientX - rect.left, e.clientY - rect.top);
      return;
    }
    drag.current = { kind: "pan", startX: e.clientX, startY: e.clientY, orig: { x: view.x, y: view.y }, moved: false };
    setIsPanning(true);
  }

  // Pressing on a node: with the Select tool, start moving it
  function handleNodeDown(e, pos, move) {
    if (e.target.closest("[data-no-drag]")) { e.stopPropagation(); return; }   // e.g. video controls
    if (tool !== "select" || spaceHeld || e.button !== 0) return;              // let it pan instead
    e.stopPropagation();
    drag.current = { kind: "node", startX: e.clientX, startY: e.clientY, orig: pos, move, moved: false };
  }

  // A drag shouldn't also count as a click (e.g. selecting a clip)
  function swallowClickAfterDrag(e) {
    if (justDragged.current) {
      e.stopPropagation();
      e.preventDefault();
      justDragged.current = false;
    }
  }

  function handleDrop(e) {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files[0]) onDropFile(e.dataTransfer.files[0]);
  }

  // Vine from the right side of the video to the left side of a clip
  const start = { x: sourcePos.x + SOURCE_SIZE.w, y: sourcePos.y + SOURCE_SIZE.h / 2 };
  function vine(node) {
    const end = { x: node.x, y: node.y + CLIP_SIZE.h / 2 };
    const bend = Math.max(60, (end.x - start.x) / 2);
    const c1 = { x: start.x + bend, y: start.y };
    const c2 = { x: end.x - bend, y: end.y };
    // Halfway along the curve, for a little leaf
    const mid = { x: (start.x + 3 * c1.x + 3 * c2.x + end.x) / 8, y: (start.y + 3 * c1.y + 3 * c2.y + end.y) / 8 };
    return { d: `M ${start.x} ${start.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${end.x} ${end.y}`, mid };
  }

  const panMode = tool === "pan" || spaceHeld;
  const cursor = isPanning ? "grabbing" : panMode ? "grab" : tool === "zoom" ? "zoom-in" : "default";

  return (
    <div
      ref={viewportRef}
      className={`bc${isDragOver ? " dragover" : ""}`}
      style={{
        cursor,
        backgroundSize: `${40 * view.zoom}px ${40 * view.zoom}px`,
        backgroundPosition: `${view.x}px ${view.y}px`,
      }}
      onPointerDown={handleCanvasDown}
      onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
      onDragLeave={() => setIsDragOver(false)}
      onDrop={handleDrop}
    >
      {/* Everything on the canvas lives in this "world", which moves and scales */}
      <div className="bc-world" style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.zoom})` }}>
        <svg className="bc-vines" width="1" height="1">
          {[...clips, ...ghosts.map((g, i) => ({ ...g, id: `ghost-${i}`, ghost: true }))].map((node) => {
            const { d, mid } = vine(node);
            return (
              <g key={node.id} className={node.ghost ? "bc-vine-ghost" : ""}>
                <path d={d} className="bc-vine" />
                <ellipse cx={mid.x} cy={mid.y} rx="13" ry="6" className="bc-leaf" transform={`rotate(-35 ${mid.x} ${mid.y})`} />
              </g>
            );
          })}
        </svg>

        <div
          className="bc-node bc-source"
          style={{ left: sourcePos.x, top: sourcePos.y, width: SOURCE_SIZE.w, height: SOURCE_SIZE.h }}
          onPointerDown={(e) => handleNodeDown(e, sourcePos, onMoveSource)}
          onClickCapture={swallowClickAfterDrag}
        >
          {renderSource()}
        </div>

        {clips.map((clip) => (
          <div
            key={clip.id}
            className="bc-node bc-clip"
            style={{ left: clip.x, top: clip.y, width: CLIP_SIZE.w, height: CLIP_SIZE.h }}
            onPointerDown={(e) => handleNodeDown(e, { x: clip.x, y: clip.y }, (pos) => onMoveClip(clip.id, pos))}
            onClickCapture={swallowClickAfterDrag}
          >
            {renderClip(clip)}
          </div>
        ))}

        {ghosts.map((ghost, i) => (
          <div
            key={`ghost-${i}`}
            className="bc-node bc-ghost"
            style={{ left: ghost.x, top: ghost.y, width: CLIP_SIZE.w, height: CLIP_SIZE.h }}
          />
        ))}
      </div>

      {/* Toolbar (top-left) */}
      <div className="bc-toolbar" onPointerDown={(e) => e.stopPropagation()}>
        {tools.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`bc-tool${tool === t.id ? " active" : ""}`}
            onClick={() => setTool(t.id)}
          >
            <span>{t.icon}</span> {t.label}
          </button>
        ))}
        <button type="button" className="bc-tool" onClick={onArrange} disabled={clips.length === 0}>
          <span>▦</span> Arrange
        </button>
      </div>

      {/* Zoom controls and extra buttons (top-right) */}
      <div className="bc-controls" onPointerDown={(e) => e.stopPropagation()}>
        {extra}
        <div className="bc-zoom">
          <button type="button" onClick={() => zoomAtCenter(1 / 1.2)} title="Zoom out">−</button>
          <span>{Math.round(view.zoom * 100)}%</span>
          <button type="button" onClick={() => zoomAtCenter(1.2)} title="Zoom in">+</button>
        </div>
        <button type="button" className="bc-fit" onClick={fitToView} title="Fit everything on screen">⛶</button>
      </div>
    </div>
  );
}

export default BranchCanvas;
