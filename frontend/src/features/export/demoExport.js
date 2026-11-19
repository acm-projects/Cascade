import { useEffect, useState } from "react";

// Demo mode: Export shows every clip as the saved finished AI edit (e.g. 0:13), whatever was done in the Editor.
// The backend says whether demo mode is on (GET …/editor/demo-export → { version, seconds }, 404 when off).
let known = null;   // { version, seconds } | false, once asked

export function useDemoExport(api, projectId) {
  const [demo, setDemo] = useState(known || null);
  useEffect(() => {
    if (known !== null) return undefined;
    let active = true;
    api.getDemoExport(projectId).then((info) => { known = info; if (active) setDemo(info); })
      .catch(() => { known = false; });
    return () => { active = false; };
  }, [api, projectId]);
  return demo || null;
}

/** The edit as Export shows it in demo mode: the clip's own AI edit if it has one, otherwise the saved demo edit. */
export function withDemoEdit(state, demo) {
  if (!state || !demo || state.ai_edit) return state;
  return { ...state, ai_edit: { version: demo.version, duration: demo.seconds } };
}
