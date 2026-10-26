import VineEdge from "./VineEdge";

// Tells React Flow which component draws each edge "type".
// Outside any component so it's the same object every render (React Flow warns otherwise).
export const edgeTypes = {
  vine: VineEdge,
};
