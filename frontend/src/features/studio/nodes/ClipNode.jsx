import { Handle, Position } from "@xyflow/react";
import ClipCard from "../../../components/ClipCard";
import { useProject } from "../../../context/ProjectContext";

// One found clip: hover to preview it, click to pick it for the Editor.
// It reads the video and the picked clips straight from the project, so picking one
// doesn't have to rebuild the whole canvas.
//   data.clip - { id, start, end }
// Drag the box by its wooden frame; the card itself is "nodrag" so a click always picks it.
function ClipNode({ data }) {
  const { sourceVideo, selectedIds, setSelectedIds } = useProject();
  const { clip } = data;
  const isSelected = selectedIds.includes(clip.id);

  function toggle() {
    setSelectedIds((current) =>
      current.includes(clip.id) ? current.filter((id) => id !== clip.id) : [...current, clip.id]
    );
  }

  return (
    <div className="studio-node studio-clip-node">
      <Handle type="target" position={Position.Left} />
      <div className="studio-clip-card nodrag">
        <ClipCard
          sourceUrl={sourceVideo?.url}
          start={clip.start}
          end={clip.end}
          isSelected={isSelected}
          onToggle={toggle}
        />
      </div>
    </div>
  );
}

export default ClipNode;
