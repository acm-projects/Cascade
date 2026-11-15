import { useEffect, useState } from "react";
import useApi from "../api/useApi";

// Picture for a project card: the first frame of the project's newest video clip.
// Remembered per project until the project changes, so going back to Projects doesn't download them again.
const remembered = new Map();   // project id -> { version, loading: Promise<picture address or null> }

function isVideoClip(clip) {
  return clip.media_kind !== "audio" && !clip.clip_url?.endsWith(".mp3");
}

async function loadThumbnail(api, projectId) {
  const { groups } = await api.listGenerations(projectId);
  for (const group of [...groups].reverse()) {   // newest generation first
    const clip = group.clips?.find(isVideoClip);
    if (clip) {
      const picture = await api.getClipThumbnail(projectId, group.job_id, clip.clip_index);
      return URL.createObjectURL(picture);
    }
  }
  return null;   // no clips yet: the card keeps its leaf
}

// Returns the picture's address, or null while loading / if there isn't one.
export default function useProjectThumbnail(project) {
  const api = useApi();
  const projectId = project.id;
  const version = project.updated_at ?? project.created_at;
  const [loaded, setLoaded] = useState(null);   // { projectId, version, url }

  useEffect(() => {
    let current = remembered.get(projectId);
    if (!current || current.version !== version) {
      current?.loading.then((old) => old && URL.revokeObjectURL(old));
      current = { version, loading: loadThumbnail(api, projectId).catch(() => null) };
      remembered.set(projectId, current);
    }
    let stillHere = true;
    current.loading.then((url) => {
      if (stillHere) setLoaded({ projectId, version, url });
    });
    return () => { stillHere = false; };
  }, [api, projectId, version]);

  return loaded?.projectId === projectId && loaded.version === version ? loaded.url : null;
}
