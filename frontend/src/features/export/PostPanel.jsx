import { useEffect, useRef, useState } from "react";
import useApi from "../../api/useApi";
import Button from "../../components/ui/Button";
import Spinner from "../../components/ui/Spinner";
import { useToast } from "../../components/ui/ToastContext";

// Post copy for one clip: title, caption and hashtags (backend/post_metadata.py, Manila).
// "Write with AI" drafts them from the clip's transcript; nothing is saved until you press Save.
//   onChange(post) - tells the page the current copy (YouTube uses it as the title/description)
// Use with key={clip key} so switching clips loads that clip's copy.
function PostPanel({ projectId, clip, onChange }) {
  const api = useApi();
  const toast = useToast();
  const [post, setPost] = useState(null);
  const [tagText, setTagText] = useState("");
  const [busy, setBusy] = useState(null); // null | "save" | "generate" | "rewrite" | "tags"
  const [dirty, setDirty] = useState(false);
  // Latest onChange/toast without re-loading the copy when the parent re-renders
  const latest = useRef({ onChange, toast });
  useEffect(() => {
    latest.current = { onChange, toast };
  });

  useEffect(() => {
    let active = true;
    api.getPost(projectId, clip.job_id, clip.clip_index)
      .then((saved) => {
        if (!active) return;
        setPost(saved);
        setTagText(saved.hashtags.join(" "));
        latest.current.onChange?.(saved);
      })
      .catch((err) => active && latest.current.toast.show(err.message, "error"));
    return () => {
      active = false;
    };
  }, [api, projectId, clip.job_id, clip.clip_index]);

  const current = () => ({ ...post, hashtags: tagText.split(/[\s,]+/).filter(Boolean) });

  function edit(field, value) {
    const next = { ...post, [field]: value };
    setPost(next);
    setDirty(true);
    onChange?.({ ...next, hashtags: tagText.split(/[\s,]+/).filter(Boolean) });
  }

  function editTags(value) {
    setTagText(value);
    setDirty(true);
    onChange?.({ ...post, hashtags: value.split(/[\s,]+/).filter(Boolean) });
  }

  async function save() {
    setBusy("save");
    try {
      const saved = await api.savePost(projectId, clip.job_id, clip.clip_index, current());
      setPost(saved);
      setTagText(saved.hashtags.join(" "));
      setDirty(false);
      onChange?.(saved);
      toast.show("Post copy saved");
    } catch (err) {
      toast.show(err.message, "error");
    } finally {
      setBusy(null);
    }
  }

  // action: "generate" | "rewrite" | "tags"
  async function suggest(action) {
    setBusy(action);
    try {
      const result = await api.generatePost(projectId, clip.job_id, clip.clip_index, action, current());
      const next = action === "tags" ? { ...post } : { ...post, caption: result.caption };
      const tags = action === "rewrite" ? tagText : result.hashtags.join(" ");
      setPost(next);
      setTagText(tags);
      setDirty(true);
      onChange?.({ ...next, hashtags: tags.split(/[\s,]+/).filter(Boolean) });
    } catch (err) {
      toast.show(err.message, "error");
    } finally {
      setBusy(null);
    }
  }

  if (!post) return <div className="export-panel-loading"><Spinner label="Loading post copy" /></div>;

  return (
    <div className="export-post">
      <h3 className="export-social-title">Post copy</h3>
      <label className="export-post-field">
        Title
        <input value={post.name} maxLength={160} onChange={(e) => edit("name", e.target.value)} />
      </label>
      <label className="export-post-field">
        Caption
        <textarea rows={3} value={post.caption} maxLength={5000} onChange={(e) => edit("caption", e.target.value)} />
      </label>
      <label className="export-post-field">
        Hashtags
        <input value={tagText} placeholder="#funny #highlights" onChange={(e) => editTags(e.target.value)} />
      </label>
      <div className="export-post-actions">
        <Button size="sm" variant="primary" onClick={save} disabled={busy !== null || !dirty}>
          {busy === "save" ? "Saving…" : dirty ? "Save" : "✓ Saved"}
        </Button>
        <Button size="sm" onClick={() => suggest(post.caption ? "rewrite" : "generate")} disabled={busy !== null}>
          {busy === "generate" || busy === "rewrite" ? "Writing…" : post.caption ? "✨ Improve with AI" : "✨ Write with AI"}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => suggest("tags")} disabled={busy !== null}>
          {busy === "tags" ? "Thinking…" : "# Suggest hashtags"}
        </Button>
      </div>
    </div>
  );
}

export default PostPanel;
