import { useRef, useState } from "react";
import useApi from "../../api/useApi";
import { useToast } from "../../components/ui/ToastContext";
import Spinner from "../../components/ui/Spinner";
import Icon from "../../components/ui/Icon";
import { VIDEO_ACCEPT, isVideoFile } from "../../utils/media";

// "Upload your own clip": puts a video straight into the Editor, no AI Studio picking needed.
//   projectId
//   onUploaded({ job_id, clip_index, ... }) - called once the clip is ready to edit
//   className, label - how the button looks
//   beforeUpload() - optional: save the clip you're on first (may throw to cancel)
function UploadClipButton({ projectId, onUploaded, beforeUpload, className = "btn btn-small", label = "Upload a clip" }) {
  const api = useApi();
  const toast = useToast();
  const input = useRef(null);
  const [busy, setBusy] = useState(false);

  async function upload(file) {
    if (!file) return;
    if (!isVideoFile(file)) {
      toast.show("Choose a video: MP4, MOV, WebM, MKV or AVI.", "error");
      return;
    }
    setBusy(true);
    try {
      await beforeUpload?.();
      const result = await api.uploadEditorClip(projectId, file);
      if (result.warning) toast.show(result.warning);
      await onUploaded(result);
    } catch (err) {
      toast.show(`Couldn't add the clip: ${err.message}`, "error");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <>
      <button type="button" className={className} disabled={busy} onClick={() => input.current.click()}
        title="Add your own video to edit (no AI picking needed)">
        {busy ? <><Spinner size={14} label="Uploading" /> Uploading…</> : <><Icon name="plus" /> {label}</>}
      </button>
      <input ref={input} type="file" accept={VIDEO_ACCEPT} hidden onChange={(e) => upload(e.target.files[0])} />
    </>
  );
}

export default UploadClipButton;
