// The Editor page's three arrangements (editorLayout.js picks one). ClipWorkspace builds the pieces
// (preview, timeline, tool panel, ...) and each layout places them.
import EmptyState from "../../components/ui/EmptyState";
import ClipPlayer from "./ClipPlayer";
import Icon from "../../components/ui/Icon";
import ClipLoading from "./ClipLoading";

const panelTabs = ["Trim", "Captions", "B-roll", "Trends", "Aspect Ratio", "Music", "Reel", "AI Editor"];
// Abhishri's layout has these tabs: trimming happens on the timeline, and Trends is a button on the player
export const splitTabs = ["Captions", "Aspect Ratio", "B-roll", "Music", "AI Editor"];
// The new layout's tool rail: [panel tab, label under the icon, icon]
const railTools = [
  ["Captions", "Captions", "captions"], ["Music", "Music", "headphones"], ["B-roll", "B-roll", "film"],
  ["Trim", "Trim", "scissors"], ["Aspect Ratio", "Aspect", "phone"], ["Trends", "Trends", "sparkles"],
  ["Reel", "Reel", "repeat"], ["AI Editor", "AI Editor", "send"],
];
// Panel title + a friendly tip for each tool (new layout only)
const panelInfo = {
  "Trim": ["Trim your clip", "Clips 15–30 seconds long do best on Reels and Shorts. Try trimming a slow start!"],
  "Captions": ["Captions", "Click a caption on the timeline to fix its words."],
  "Music": ["Add music", "Keep music quiet under talking so every word is easy to hear."],
  "B-roll": ["B-roll", "Drop B-roll over the boring parts to keep people watching."],
  "Aspect Ratio": ["Aspect ratio", "9:16 fills a phone screen: best for Reels, Shorts and TikTok."],
  "Reel": ["Make a reel", "Mix your best moments into one fast reel."],
  "AI Editor": ["AI Editor", "Say what you want, like \"make the captions yellow\"."],
};

// ---------- New layout (Figma "Editor Page – Revamp") ----------
export function RevampLayout({ info, state, panelTab, setPanelTab, setTrendsOpen, goToExport, clipTabs, preview, undoRedo, statuses, timeline, panelContent, trendsModal }) {
  const tool = panelTab; // the tool that's lit up in the rail
  const [title, tip] = panelInfo[tool] ?? panelInfo["AI Editor"];
  function chooseTool(id) {
    if (id === "Trends") return setTrendsOpen(true);
    if (id === "B-roll") return setPanelTab("B-roll");
    setPanelTab(id);
  }
  const unavailable = (id) => (id === "Aspect Ratio" || id === "B-roll") && info?.has_video === false;

  return (
    <>
      <div className="er-body">
        <nav className="er-rail" aria-label="Editor tools">
          {railTools.map(([id, label, icon]) => (
            <button key={id} type="button" className={`er-tool${id === tool ? " active" : ""}`}
              aria-pressed={id === tool} disabled={!state || unavailable(id)}
              title={unavailable(id) ? "Audio recordings have no video" : undefined}
              aria-haspopup={id === "Trends" ? "dialog" : undefined} onClick={() => chooseTool(id)}>
              <Icon name={icon} size={30} />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <aside className="er-panel">
          <h2 className="er-panel-title">{title}</h2>
          <div className="er-panel-content editor-panel-content">{panelContent}</div>
          <div className="er-tip">
            <span className="er-tip-mascot" aria-hidden="true"><Icon name="leaf" size={26} /></span>
            <p><strong>Tip</strong>{tip}</p>
          </div>
        </aside>

        <main className="er-stage">
          {clipTabs}
          <section className="er-preview">{preview}</section>
          <div className="er-stage-bar">
            {undoRedo}
            {statuses}
            <button type="button" className="btn btn-small btn-primary er-export" onClick={goToExport}>Go to Export <Icon name="chevronRight" /></button>
          </div>
          {info?.warning && <p className="editor-warning">{info.warning}</p>}
        </main>

        {timeline && <section className="er-timeline" aria-label="Timeline">{timeline}</section>}
      </div>
      {trendsModal}
    </>
  );
}

// ---------- Abhishri's layout (from davebranch) ----------
export function SplitLayout({ info, state, draft, projectId, clip, player, setPanelTab, activeTab, trendsOpen, setTrendsOpen, goToExport, clipTabs, undoRedo, statuses, timeline, panelContent, trendsModal }) {
  return (
    <>
      <div className="es-body">
        <section className="es-preview">
          <nav className="es-clip-rail" aria-label="Select clip">{clipTabs}</nav>
          <div className="es-preview-player">
          {draft.error ? (
            <EmptyState icon="cloud" title="Couldn't load this clip" text={draft.error.message} />
          ) : info && state ? (
            <ClipPlayer projectId={projectId} clip={clip} info={info} state={state} controlRef={player} saveStatus={statuses}
              framing={{ patch: draft.patch, recordUndo: draft.recordUndo }} />
          ) : (
            <ClipLoading />
          )}
          </div>
        </section>
        <aside className="es-panel">
          <div className="es-panel-workspace">
          <div className="editor-panel-tabs">
            <button type="button" className="btn btn-small btn-primary es-export" onClick={goToExport}>Export →</button>
            <div className="es-history">{undoRedo}</div>
            {splitTabs.map((tab) => (
              <button key={tab} type="button" className={`editor-panel-tab${tab === activeTab ? " active" : ""}`}
                disabled={info?.has_video === false && ["Aspect Ratio", "B-roll"].includes(tab)}
                title={info?.has_video === false && ["Aspect Ratio", "B-roll"].includes(tab) ? "Audio recordings have no video" : undefined}
                aria-label={tab} aria-pressed={tab === activeTab}
                onClick={() => setPanelTab(tab)}>
                <Icon name={railTools.find(([id]) => id === tab)?.[2]} size={22} />
                <span className="es-tab-label">{tab}</span>
              </button>
            ))}
          </div>
          <div className="editor-panel-content">
            {panelContent}
            {/* Trends: in the top-right corner of the tool area, next to the tab's own controls. It's inside the
                scrolling part, so it scrolls away with the controls instead of floating over them. */}
            <button type="button" className="btn btn-small btn-primary es-trends es-trends-corner"
              disabled={!state || info?.has_video === false} aria-haspopup="dialog" aria-expanded={trendsOpen}
              onClick={() => setTrendsOpen(true)}>
              <Icon name="sparkles" size={18} /> Trends
            </button>
          </div>
          </div>
        </aside>
        {timeline && <section className="es-timeline" aria-label="Timeline">{timeline}</section>}
        {info?.warning && <p className="es-warning editor-warning">{info.warning}</p>}
      </div>
      {trendsModal}
    </>
  );
}

// ---------- Classic layout ----------
export function ClassicLayout({ info, state, panelTab, setPanelTab, trendsOpen, setTrendsOpen, goToExport, sidebar, preview, undoRedo, statuses, timeline, panelContent, trendsModal }) {
  return (
    <>
      <div className="editor-tools">
        {undoRedo}
        {statuses}
        <button type="button" className="btn btn-small btn-primary editor-export" onClick={goToExport}>Go to Export →</button>
      </div>

      <div className="editor-body">
        <div className="editor-left-column">
          {sidebar}
        </div>

        <main className={`editor-center${state?.fablecut ? ' has-ai-sequence' : ''}`}>
          <section className="editor-preview">{preview}</section>
          {timeline && <section className="editor-timeline" aria-label="Timeline">{timeline}</section>}
          {info?.warning && <p className="editor-warning">{info.warning}</p>}
        </main>

        <aside className="editor-panel">
          <div className="editor-panel-tabs">
            {panelTabs.map((tab) => (
              <button key={tab} type="button" className={`editor-panel-tab${tab === panelTab ? " active" : ""}`}
                disabled={info?.has_video === false && ["Aspect Ratio", "B-roll"].includes(tab)}
                title={info?.has_video === false && ["Aspect Ratio", "B-roll"].includes(tab) ? 'Audio recordings have no video' : undefined}
                aria-haspopup={tab === 'Trends' ? 'dialog' : undefined}
                aria-expanded={tab === 'Trends' ? trendsOpen : undefined}
                onClick={() => tab === 'Trends' ? setTrendsOpen(true) : setPanelTab(tab)}>{tab}</button>
            ))}
          </div>
          <div className="editor-panel-content">{panelContent}</div>
        </aside>
      </div>
      {trendsModal}
    </>
  );
}
