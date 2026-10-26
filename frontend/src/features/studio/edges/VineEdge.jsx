import { BaseEdge } from "@xyflow/react";
import "./VineEdge.css";

// A leafy vine between two boxes, drawn like the painted vines in assets/vines.png:
// a dark-outlined green stem with pointy leaves growing off both sides.
// (The painted vines are fixed corner art, so they can't bend along a branch; these leaves are drawn in code.)
//
// The stem is the same S-curve React Flow normally draws from a box's right side to the next box's left side.

const LEAF_GAP = 58;        // roughly one leaf every 58px of vine
const LEAF_ANGLE = 52;      // how far leaves point away from the stem (degrees)

// How far the curve's "handles" stick out (matches React Flow's own bezier edges)
function controlOffset(distance) {
  return distance >= 0 ? 0.5 * distance : 0.25 * 25 * Math.sqrt(-distance);
}

// A point on the curve and which way it's heading, for t from 0 (start) to 1 (end)
function pointOnCurve(p0, p1, p2, p3, t) {
  const u = 1 - t;
  const x = u * u * u * p0.x + 3 * u * u * t * p1.x + 3 * u * t * t * p2.x + t * t * t * p3.x;
  const y = u * u * u * p0.y + 3 * u * u * t * p1.y + 3 * u * t * t * p2.y + t * t * t * p3.y;
  const dx = 3 * u * u * (p1.x - p0.x) + 6 * u * t * (p2.x - p1.x) + 3 * t * t * (p3.x - p2.x);
  const dy = 3 * u * u * (p1.y - p0.y) + 6 * u * t * (p2.y - p1.y) + 3 * t * t * (p3.y - p2.y);
  return { x, y, angle: (Math.atan2(dy, dx) * 180) / Math.PI };
}

// A small number from the edge's id, so each vine's leaves vary a bit but never jump around
function seed(text) {
  let hash = 0;
  for (const char of text) hash = (hash * 31 + char.charCodeAt(0)) % 997;
  return hash;
}

function VineEdge({ id, sourceX, sourceY, targetX, targetY, style }) {
  const start = { x: sourceX, y: sourceY };
  const end = { x: targetX, y: targetY };
  const offset = controlOffset(targetX - sourceX);
  const c1 = { x: sourceX + offset, y: sourceY };
  const c2 = { x: targetX - offset, y: targetY };
  const path = `M${start.x},${start.y} C${c1.x},${c1.y} ${c2.x},${c2.y} ${end.x},${end.y}`;

  // Spread leaves along the middle of the vine, alternating sides
  const length = Math.hypot(targetX - sourceX, targetY - sourceY);
  const count = Math.max(2, Math.floor(length / LEAF_GAP));
  const wiggle = seed(id);
  const leaves = Array.from({ length: count }, (_, i) => {
    const t = 0.14 + (0.72 * (i + 0.5)) / count;
    const side = i % 2 === 0 ? -1 : 1;
    const size = 0.85 + (((wiggle + i * 37) % 30) / 100);   // 0.85 - 1.15
    return { ...pointOnCurve(start, c1, c2, end, t), side, size };
  });

  return (
    <>
      {/* Dark outline under the green stem, like the painted art */}
      <path d={path} className="vine-outline" />
      <BaseEdge id={id} path={path} style={style} className="vine-stem" />
      <g className="vine-leaves">
        {leaves.map((leaf, i) => (
          <g
            key={i}
            transform={`translate(${leaf.x} ${leaf.y}) rotate(${leaf.angle + leaf.side * LEAF_ANGLE}) scale(${leaf.size})`}
          >
            {/* Pointy leaf shape (pointing right from where it joins the stem) */}
            <path className="vine-leaf" d="M0,0 C5,-8 15,-9 24,0 C15,9 5,8 0,0 Z" />
            <path className="vine-leaf-vein" d="M2,0 L20,0" />
          </g>
        ))}
      </g>
    </>
  );
}

export default VineEdge;
