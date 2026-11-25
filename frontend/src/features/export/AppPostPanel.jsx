import { useState } from "react";
import Button from "../../components/ui/Button";
import Spinner from "../../components/ui/Spinner";
import Icon from "../../components/ui/Icon";
import { postText } from "./downloads";

// TikTok and Instagram on Export's "Publish online". There's no posting backend for them yet, so the button does
// what you'd do by hand: it copies the caption and hashtags, opens the app's upload page in a new tab, and
// downloads the edited video (rendered with your edits, like Download) for you to pick there.
// When direct posting is added, this panel is where its Connect & post button goes.
const APPS = {
  tiktok: { name: "TikTok", icon: "tiktok", upload: "https://www.tiktok.com/upload",
    steps: "On TikTok, choose the downloaded video and paste the caption." },
  instagram: { name: "Instagram", icon: "instagram", upload: "https://www.instagram.com/",
    steps: "On Instagram, click Create, choose the downloaded video and paste the caption." },
};

export default function AppPostPanel({ app, clip, clipNumber, post, state, downloads, flush }) {
  const { name, icon, upload, steps } = APPS[app];
  const [status, setStatus] = useState(null);   // null | "working" | "done" | { error }
  const vertical = state?.composition?.ratio === "9:16";

  async function prepare() {
    if (status === "working") return;
    const text = postText(post);
    // Both need the click itself, so they happen before the render
    const copied = text ? navigator.clipboard?.writeText(text).then(() => true, () => false) : Promise.resolve(false);
    window.open(upload, "_blank", "noopener");
    setStatus("working");
    let result = null;
    try { await flush?.(); result = await downloads.downloadOne(clip, clipNumber); } catch { /* shown below */ }
    setStatus(result ? { done: true, copied: await copied } : { error: "Couldn't render the video. Try again." });
  }

  return (
    <div className="export-publish-row">
      <h3 className="export-social-title"><Icon name={icon} /> {name}</h3>
      <div className="export-publish-controls">
        <Button size="sm" variant="primary" onClick={prepare} disabled={!state || status === "working" || downloads.working}>
          {status === "working" ? <><Spinner size={14} label="Rendering" /> Getting it ready…</> : `Post to ${name}`}
        </Button>
      </div>
      <p className="export-social-note">
        Downloads your edited video, copies the caption and opens {name}. One-click posting is coming soon.
        {!vertical && ` ${name} looks best at 9:16: change the aspect ratio in the Editor.`}
      </p>
      {status?.done && (
        <p className="export-upload-status" role="status">
          Video downloaded{status.copied ? " and caption copied" : ""}. {steps}
        </p>
      )}
      {status?.error && <p className="export-upload-status failed" role="alert">{status.error}</p>}
    </div>
  );
}
