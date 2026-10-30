import SourceNode from "./SourceNode";
import GenerationNode from "./GenerationNode";
import ClipNode from "./ClipNode";
import "./nodes.css";

// Tells React Flow which component draws each node "type" (the types graph.js uses).
// It lives outside any component so it's the same object every render (React Flow warns otherwise).
export const nodeTypes = {
  source: SourceNode,
  generation: GenerationNode,
  clip: ClipNode,
};
