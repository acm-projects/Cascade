import { useCallback, useEffect, useRef, useState } from "react";
import useApi from "../../api/useApi";

const POLL_MS = 2400;
const isRunning = (group) => ["queued", "processing"].includes(group.state);

// Everything the AI Studio page needs from the backend, in one place.
//   studio  - the studio document (sessions, messages, positions, checked clips); null until loaded
//   groups  - every generation in the project, with its clips (api.listGenerations)
//   refresh - load both again (after sending a prompt, retrying, ...)
//   setStudio - change the document locally right away (e.g. checking a clip) before the server answers
// While any generation is queued/processing it refreshes every 2.4s, and stops when none are
// (or when you leave the page).
export default function useStudioData(projectId) {
  const api = useApi();
  const [studio, setStudio] = useState(null);
  const [groups, setGroups] = useState([]);
  const [error, setError] = useState(null);
  const loadCount = useRef(0);

  // State only changes once the backend answers (never straight away)
  const refresh = useCallback(() => {
    const thisLoad = ++loadCount.current;
    return Promise.all([api.getStudio(projectId), api.listGenerations(projectId)])
      .then(([document, listing]) => {
        if (thisLoad !== loadCount.current) return; // a newer refresh already answered
        setStudio(document);
        setGroups(listing.groups);
        setError(null);
      })
      .catch((err) => {
        if (thisLoad === loadCount.current) setError(err);
      });
  }, [api, projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Keep asking "is it done yet?" only while something is still being generated
  const running = groups.some(isRunning);
  useEffect(() => {
    if (!running) return;
    const timer = setTimeout(refresh, POLL_MS);
    return () => clearTimeout(timer);
  }, [running, groups, refresh]);

  return { studio, setStudio, groups, error, refresh };
}
