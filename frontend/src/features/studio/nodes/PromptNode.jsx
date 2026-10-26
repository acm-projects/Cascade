import { Handle, Position } from "@xyflow/react";
import Spinner from "../../../components/ui/Spinner";

// A prompt you typed in the chat. Its clips grow out of its right side.
//   data.text     - the prompt
//   data.loading  - true while the (pretend) AI is finding clips
function PromptNode({ data }) {
  return (
    <div className="studio-node studio-prompt-node">
      <Handle type="target" position={Position.Left} />
      <span className="studio-prompt-text">💬 {data.text}</span>
      {data.loading && (
        <span className="studio-prompt-loading">
          <Spinner size={14} label="Finding clips" /> Finding clips…
        </span>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

export default PromptNode;
