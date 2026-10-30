import { useMemo } from "react";
import { useAuthToken } from "../auth/AuthContext";
import * as projects from "./projects";
import * as generations from "./generations";
import * as editor from "./editor";
import * as features from "./features";
import * as studio from "./studio";
import * as posting from "./posting";

const endpoints = { ...projects, ...generations, ...editor, ...features, ...studio, ...posting };

// Every api function takes the sign-in token first: listProjects(token).
// This hook hands you the same functions with the token already filled in, so in a component you write:
//   const api = useApi();
//   const { projects } = await api.listProjects();
//   await api.deleteProject(projectId);
export default function useApi() {
  const getToken = useAuthToken();

  // useMemo: build the object once (not on every render), so it's safe to use in useEffect dependencies
  return useMemo(() => {
    const api = {};
    for (const [name, fn] of Object.entries(endpoints)) {
      if (name === "audioAssetPath") continue;
      api[name] = async (...args) => fn(await getToken(), ...args);
    }
    return api;
  }, [getToken]);
}
