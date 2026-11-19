import { formatTime } from "../../utils/time";
import { useClipLength } from "./aiFilm";

/** A clip's length as text: the finished AI edit's length when it has one (0:13), otherwise the clip's (1:40). */
export default function ClipLength({ projectId, clip }) {
  return formatTime(useClipLength(projectId, clip));
}
