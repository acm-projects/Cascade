import { Handle, Position } from "@xyflow/react";

// Compact canvas waypoint; the chat owns the prompt and generation controls.
function GenerationNode({ data }) {
  const { group, number, onFocusPrompt, referenceLabels = [] } = data;
  const context = referenceLabels.length > 1
    ? `Combines ${referenceLabels.map(ref => `Clip ${ref.label}`).join(" + ")}. ` : "";

  return (
    <div className={`studio-prompt-pad is-${group.state}`}>
      <Handle type="target" position={Position.Left} />
      <button type="button" className="studio-pad-button nodrag nopan"
        onClick={() => onFocusPrompt?.(group.job_id)}
        aria-label={`Go to prompt ${number} in AI chat: ${group.prompt}`}
        title={`${context}${group.prompt}\nOpen this prompt in AI chat`}>
        <svg viewBox="0 0 130 100" aria-hidden="true">
          <path className="studio-pad-shadow" d="M64 8C28 3 5 23 5 49s22 43 56 44c35 1 64-16 64-44 0-14-8-26-21-33L69 46 82 10C76 9 70 8 64 8Z" />
          <path className="studio-pad-leaf" d="M64 4C28-1 5 19 5 45s22 43 56 44c35 1 64-16 64-44 0-14-8-26-21-33L69 42 82 6C76 5 70 4 64 4Z" />
          <path className="studio-pad-veins" d="M68 44 24 22M68 44 12 48M68 44 29 74M68 44 65 84M68 44 109 69" />
        </svg>
        <span className="studio-pad-label">P{number}</span>
      </button>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

export default GenerationNode;
