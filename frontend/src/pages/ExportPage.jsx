import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import "./ExportPage.css";
import TopNav from "../components/TopNav";
import { markPageReady, useLeafNavigate } from "../context/leafTransitionValue";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import Spinner from "../components/ui/Spinner";
import { useToast } from "../components/ui/ToastContext";
import useApi from "../api/useApi";
import { formatTime } from "../utils/time";
import { clipKey, flattenClips } from "../features/editor/clips";
import useClipDraft from "../features/editor/useClipDraft";
import useAutoFraming from "../features/editor/useAutoFraming";
import ClipPlayer from "../features/editor/ClipPlayer";
import useDownloads from "../features/export/useDownloads";
import ExportSettings from "../features/export/ExportSettings";
import PostPanel from "../features/export/PostPanel";
import YouTubePanel from "../features/export/YouTubePanel";
import LinkedInPanel from "../features/export/LinkedInPanel";
import { isAudioClip } from "../utils/media";
import TrendsModal from "../features/editor/TrendsModal";
import { exportTree } from "../features/export/exportTree";
import Icon from "../components/ui/Icon";

// Export, laid out as four steps across the top (Select clips > Preview > Configure > Export) and three columns:
//   left   - 1. pick which clips to export (session > wave > clip), 2. choose where they go (a file, or YouTube)
//   middle - the clip on screen (Original / Edited) with a strip of every clip under it
//   right  - 3. the export settings and the big Export button (or, for YouTube, the post copy and upload)
// Connected to backend/editor_backend.py (rendering) and Manila's posting backend. Every download is rendered
// by the server with your edits.
const STEPS = [
  { id: "select", label: "Select clips", icon: "check" },
  { id: "preview", label: "Preview", icon: "play" },
  { id: "configure", label: "Configure", icon: "sliders" },
  { id: "export", label: "Export", icon: "download" },
];

function ExportPage() {
  const navigate = useNavigate();
  const leafNavigate = useLeafNavigate();
  const { projectId } = useParams();
  const api = useApi();
  const [clips, setClips] = useState(null);
  const [error, setError] = useState(null);
  const [projectName, setProjectName] = useState(null);
  const [currentKey, setCurrentKey] = useState(null);
  const [inZip, setInZip] = useState([]);       // clip keys to export
  const [settings, setSettings] = useState({ resolution: "original", includeCaptions: true });
  const [destination, setDestination] = useState("download");   // "download" | "youtube"
  const [configured, setConfigured] = useState(false);          // touched a setting: step 3 is underway
  const downloads = useDownloads(api, projectId, projectName, settings);
  const activeFlush = useRef(null);
  const registerFlush = useCallback((fn) => { activeFlush.current = fn; }, []);
  const toast = useToast();

  useEffect(() => {
    let active = true;
    Promise.all([api.getEditorIndex(projectId, { selectedOnly: true }), api.getProject(projectId)])
      .then(([index, project]) => {
        if (!active) return;
        const list = flattenClips(index);
        setClips(list);
        setProjectName(project.name);
        setCurrentKey(list[0] && clipKey(list[0]));
        setInZip(list.map(clipKey));
      })
      .catch((err) => active && setError(err));
    return () => {
      active = false;
    };
  }, [api, projectId]);

  const current = clips?.find((clip) => clipKey(clip) === currentKey);
  // Nothing more to load (an error, or no clips): the waterfall can fall away. Otherwise ClipExport says when.
  const settled = Boolean(error || (clips && !clips.length));
  useEffect(() => { if (settled) markPageReady(); }, [settled]);
  const tree = useMemo(() => exportTree(clips ?? []), [clips]);
  const picked = clips?.filter((clip) => inZip.includes(clipKey(clip))) ?? [];

  // Which step the bar highlights
  let step = "preview";
  if (!picked.length) step = "select";
  else if (downloads.progressText === "Download ready.") step = "export";
  else if (configured) step = "configure";

  const downloadZip = async () => {
    try { await activeFlush.current?.(); await downloads.downloadSelected(picked); }
    catch (err) { toast.show(err.message, "error"); }
  };

  async function pickClip(key) {
    try { await activeFlush.current?.(); setCurrentKey(key); }
    catch (err) { toast.show(err.message, "error"); }
  }

  async function leave(to) {
    try { await activeFlush.current?.(); leafNavigate(to, { style: "falls" }); }   // a waterfall covers the change
    catch (err) { toast.show(err.message, "error"); }
  }

  // Checkboxes: one clip, or every clip in a wave/session at once
  const allIn = (list) => list.every((clip) => inZip.includes(clipKey(clip)));
  function toggleGroup(list) {
    const keys = list.map(clipKey);
    setInZip((now) => (allIn(list) ? now.filter((k) => !keys.includes(k)) : [...new Set([...now, ...keys])]));
  }

  let message;
  if (error) message = <EmptyState icon="cloud" title="Couldn't open Export" text={error.message} />;
  else if (!clips) message = <Spinner size={48} label="Loading your clips" />;
  else if (!clips.length) {
    message = (
      <EmptyState icon="box" title="Nothing to export yet" text="Pick clips on Studio Island and edit them, then export them here."
        action={{ label: "Go to Studio Island", onClick: () => leafNavigate(`/projects/${projectId}/studio`, { style: "falls" }) }} />
    );
  }

  const audioOnly = isAudioClip(current);

  return (
    <div className="export leaf-page">
      <TopNav projectTitle={projectName} active="export" canOpenEditor canOpenExport />
      {message ? (
        <div className="export-empty">{message}</div>
      ) : (
        <>
          <div className="export-top">
            <Button size="sm" className="export-back" onClick={() => leave(`/projects/${projectId}/editor`)}>
              ← Back to editor
            </Button>
            <StepBar step={step} />
          </div>

          <div className="export-body">
            <aside className="export-panel export-left" aria-label="Clips and destination">
              <section aria-labelledby="export-select-title">
                <header className="export-panel-head">
                  <h2 id="export-select-title" className="export-panel-title">1. Select clips</h2>
                  <span className="export-count">{inZip.length} selected</span>
                </header>
                <div className="export-tree">
                  {tree.map((session) => {
                    const sessionClips = session.waves.flatMap((wave) => wave.clips);
                    return (
                      <TreeGroup key={session.id} label={session.name} checked={allIn(sessionClips)}
                        onCheck={() => toggleGroup(sessionClips)}>
                        {session.waves.map((wave) => (
                          <TreeGroup key={wave.id} label={wave.name} title={wave.prompt} checked={allIn(wave.clips)}
                            onCheck={() => toggleGroup(wave.clips)}>
                            {wave.clips.map((clip) => {
                              const key = clipKey(clip);
                              return (
                                <div key={key} className="export-tree-clip">
                                  <input type="checkbox" checked={inZip.includes(key)} onChange={() => toggleGroup([clip])}
                                    aria-label={`Include clip ${clips.indexOf(clip) + 1} in the export`} />
                                  <button type="button" className={`export-tree-clip-name${key === currentKey ? " active" : ""}`}
                                    onClick={() => pickClip(key)} title={clip.title}>
                                    <span>Clip {clips.indexOf(clip) + 1}</span>
                                    <span className="export-tree-time">{formatTime(clip.end - clip.start)}</span>
                                  </button>
                                </div>
                              );
                            })}
                          </TreeGroup>
                        ))}
                      </TreeGroup>
                    );
                  })}
                </div>
                <button type="button" className="export-link"
                  onClick={() => setInZip(inZip.length === clips.length ? [] : clips.map(clipKey))}>
                  {inZip.length === clips.length ? "Clear all" : "Select all"}
                </button>
              </section>

              <section className="export-destinations" aria-labelledby="export-destination-title">
                <h2 id="export-destination-title" className="export-panel-title">2. Choose destination</h2>
                <Destination value="download" chosen={destination} onChoose={(value) => { setDestination(value); setConfigured(true); }}
                  icon="download" title="Download file" text="Export a video to your device" />
                <Destination value="youtube" chosen={destination} onChoose={(value) => { setDestination(value); setConfigured(true); }}
                  icon="youtube" title="Publish online" text="Post to YouTube or LinkedIn" disabled={audioOnly} />
                <p className="export-tip">
                  <Icon name="sparkles" />
                  You can add a title, caption and hashtags when you publish to YouTube.
                </p>
              </section>
            </aside>

            <ClipExport key={currentKey} projectId={projectId} clip={current} clips={clips} picked={picked}
              downloads={downloads} registerFlush={registerFlush} onPick={pickClip} onDownloadSelected={downloadZip}
              clipNumber={clips.indexOf(current) + 1} destination={destination} settings={settings}
              onSettings={(next) => { setSettings(next); setConfigured(true); }}
              onAddClip={() => leave(`/projects/${projectId}/studio`)} onDone={() => navigate("/projects")}
              onOpenEditor={() => leave(`/projects/${projectId}/editor`)}
            />
          </div>
        </>
      )}
    </div>
  );
}

// Select clips > Preview > Configure > Export. Steps before the current one get a check mark.
function StepBar({ step }) {
  const at = STEPS.findIndex((item) => item.id === step);
  return (
    <ol className="export-steps" aria-label="Export steps">
      {STEPS.map((item, i) => {
        const state = i < at ? "done" : i === at ? "current" : "next";
        return (
          <Fragment key={item.id}>
            {i > 0 && <li className="export-step-arrow" aria-hidden="true"><Icon name="chevronRight" /></li>}
            <li className={`export-step is-${state}`} aria-current={state === "current" ? "step" : undefined}>
              <span className="export-step-icon"><Icon name={state === "done" ? "check" : item.icon} /></span>
              {item.label}
            </li>
          </Fragment>
        );
      })}
    </ol>
  );
}

// One "where should it go" choice: a radio button styled as a card
function Destination({ value, chosen, onChoose, icon, title, text, disabled }) {
  return (
    <label className={`export-destination${chosen === value ? " active" : ""}${disabled ? " is-disabled" : ""}`}>
      <input type="radio" name="export-destination" value={value} checked={chosen === value} disabled={disabled}
        onChange={() => onChoose(value)} />
      <Icon name={icon} className={`export-destination-icon is-${value}`} />
      <span>
        <b>{title}</b>
        <small>{disabled ? "Audio clips can only be downloaded" : text}</small>
      </span>
    </label>
  );
}

// A folder in the left list (a session or a wave): fold it, tick all its clips, then its contents
function TreeGroup({ label, title, checked, onCheck, children }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="export-tree-group">
      <div className="export-tree-row" title={title}>
        <button type="button" className="export-tree-fold" onClick={() => setOpen(!open)}
          aria-expanded={open} aria-label={`${open ? "Fold" : "Unfold"} ${label}`}><Icon name={open ? "chevronDown" : "chevronRight"} /></button>
        <input type="checkbox" checked={checked} onChange={onCheck} aria-label={`Include all of ${label}`} />
        <span>{label}</span>
      </div>
      {open && <div className="export-tree-children">{children}</div>}
    </div>
  );
}

// The middle and right columns, for the clip on screen. key={clip key}, so it follows the chosen clip.
function ClipExport({ projectId, clip, clips, picked, onPick, onDownloadSelected, downloads, clipNumber, registerFlush,
  destination, settings, onSettings, onAddClip, onDone, onOpenEditor }) {
  const toast = useToast();
  const draft = useClipDraft(projectId, clip);
  const [trendsOpen, setTrendsOpen] = useState(false);
  const { info, state, error, patch } = draft;
  const loaded = Boolean((info && state) || error);
  useEffect(() => { if (loaded) markPageReady(); }, [loaded]);   // the clip on screen is ready
  useEffect(() => { registerFlush(draft.flush); return () => registerFlush(null); }, [registerFlush, draft.flush]);
  // Fill (crop) exports need the framing analysis first; this starts it if the Editor didn't finish it
  const framing = useAutoFraming(projectId, clip, state, info, patch);
  const rendering = downloads.working;
  const [rendered, setRendered] = useState(null); // the last MP4, so it can be shared
  const [post, setPost] = useState(null);
  const audioOnly = isAudioClip(clip);
  const notReady = !state || rendering || framing.status === "working";

  async function downloadMp4() {
    try {
      await draft.flush();
      const result = await downloads.downloadOne(clip, clipNumber);
      if (result) setRendered(new File([result.blob], result.filename, { type: result.blob.type }));
    } catch (err) { toast.show(err.message, "error"); }
  }

  // The big button: just this clip as an MP4 (it can then be shared), or every picked clip as a ZIP
  const onlyThisClip = picked.length === 1 && clipKey(picked[0]) === clipKey(clip);
  const exportPicked = onlyThisClip ? downloadMp4 : onDownloadSelected;

  // Instagram/TikTok/etc. have no upload API for us, so hand the file to the phone/computer's share sheet
  const canShare = rendered && navigator.canShare?.({ files: [rendered] });
  async function share() {
    try {
      await navigator.share({ files: [rendered], text: [post?.caption, ...(post?.hashtags ?? [])].filter(Boolean).join(" ") });
    } catch (err) {
      if (err.name !== "AbortError") toast.show(`Sharing failed: ${err.message}`, "error");
    }
  }

  const index = clipNumber - 1;
  const goTo = (i) => onPick(clipKey(clips[i]));
  let status = null;
  if (framing.status === "error") status = `Couldn't prepare framing: ${framing.message}`;
  else if (framing.status === "working") status = `Preparing automatic framing… ${Math.round(framing.progress * 100)}%`;
  else if (state) {
    status = `${formatTime(state.end - state.start)} · ${audioOnly ? "Audio"
      : state.composition.ratio === "original" ? "Original" : state.composition.ratio} · captions ${state.captions.enabled ? "on" : "off"}`;
  }

  return (
    <>
      <main className="export-panel export-middle" aria-label="Preview">
        <header className="export-panel-head">
          <h2 className="export-panel-title">
            Clip {clipNumber} <span className="export-clip-title" title={clip.title}>{clip.title || "Preview"}</span>
          </h2>
          <div className="export-pager">
            <button type="button" onClick={() => goTo(index - 1)} disabled={index === 0} aria-label="Previous clip">
              <Icon name="chevronRight" className="export-flip" />
            </button>
            <span>{clipNumber} of {clips.length}</span>
            <button type="button" onClick={() => goTo(index + 1)} disabled={index === clips.length - 1} aria-label="Next clip">
              <Icon name="chevronRight" />
            </button>
          </div>
        </header>

        <div className="export-player">
          {error ? <p role="alert">{error.message}</p>
            : info && state ? <ClipPlayer projectId={projectId} clip={clip} info={info} state={state} />
              : <Spinner label="Loading clip" />}
        </div>

        {/* Every clip, as a strip of cards; the last card goes back to AI Studio to pick more */}
        <div className="export-strip" aria-label="Clips">
          {clips.map((item, i) => (
            <button key={clipKey(item)} type="button" className={`export-strip-card${i === index ? " active" : ""}`}
              onClick={() => goTo(i)} aria-label={`Clip ${i + 1}: ${item.title || "clip"}`} aria-current={i === index}>
              <span className="export-strip-play"><Icon name="play" /></span>
              <b>Clip {i + 1}</b>
              <span className="export-strip-time">{formatTime(item.end - item.start)}</span>
            </button>
          ))}
          <button type="button" className="export-strip-card export-strip-add" onClick={onAddClip}>
            <Icon name="plus" />
            Add clip
          </button>
        </div>

        {status && <p className={`export-status${framing.status === "error" ? " is-error" : ""}`} role="status">{status}</p>}
      </main>

      <aside className="export-panel export-right" aria-label={destination === "youtube" ? "Publish online" : "Configure export"}>
        {destination === "youtube" && !audioOnly ? (
          <>
            <h2 className="export-panel-title">3. Publish online</h2>
            <PostPanel projectId={projectId} clip={clip} onChange={setPost} />
            {state && (
              <Button size="sm" className="export-trends-button" aria-haspopup="dialog" onClick={() => setTrendsOpen(true)}>
                <Icon name="compass" /> Trends analysis
              </Button>
            )}
            <section className="export-publish" aria-label="Publish">
              <YouTubePanel projectId={projectId} clip={clip} post={post} state={state} />
              <LinkedInPanel key={`${projectId}:${clip.job_id}:${clip.clip_index}`} projectId={projectId} clip={clip} post={post} state={state} />
            </section>
          </>
        ) : (
          <>
            <h2 className="export-panel-title">3. Configure export</h2>
            <ExportSettings settings={settings} onChange={onSettings} downloads={downloads}
              selectedCount={picked.length} audioOnly={audioOnly} />
            <div className="export-go">
              <button type="button" className="export-go-button" onClick={exportPicked} disabled={notReady || !picked.length}>
                {rendering ? <><Spinner size={18} label="Rendering" /> Rendering…</>
                  : <><Icon name="download" /> Export {picked.length} {picked.length === 1 ? "clip" : "clips"}</>}
              </button>
              <p className="export-go-note">
                {!picked.length ? "Tick at least one clip on the left."
                  : onlyThisClip ? `Downloads one ${audioOnly ? "MP3" : "MP4"} with your edits.`
                    : `Downloads a ZIP of ${picked.length} clips with your edits.`}
              </p>
              {!onlyThisClip && (
                <button type="button" className="export-link" onClick={downloadMp4} disabled={notReady}>
                  Download only clip {clipNumber}
                </button>
              )}
            </div>
            {rendered && (
              <div className="export-post">
                <h3 className="export-social-title"><Icon name={audioOnly ? "headphones" : "phone"} /> Share clip</h3>
                <p className="export-social-note">
                  {canShare ? "Share the file you just downloaded to any app on this device."
                    : "This browser can't share files. Upload the downloaded file in the app."}
                </p>
                {canShare && <Button size="sm" onClick={share}>Share…</Button>}
              </div>
            )}
            {downloads.progressText === "Download ready." && (
              <button type="button" className="export-link" onClick={onDone}>All done? Back to projects →</button>
            )}
          </>
        )}
        {trendsOpen && state && (
          <TrendsModal projectId={projectId} clip={clip} info={info} state={state} flush={draft.flush} change={draft.change}
            onClose={() => setTrendsOpen(false)} onOpenEditor={async () => { await draft.flush(); onOpenEditor(); }} />
        )}
      </aside>
    </>
  );
}

export default ExportPage;
