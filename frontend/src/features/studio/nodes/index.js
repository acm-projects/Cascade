import SourceNode from "./SourceNode";
import PromptNode from "./PromptNode";
import ClipNode from "./ClipNode";
import "./nodes.css";

// Tells React Flow which component draws each node "type".
// It lives outside any component so it's the same object every render (React Flow warns otherwise).
export const nodeTypes = {
  source: SourceNode,
  prompt: PromptNode,
  clip: ClipNode,
};
