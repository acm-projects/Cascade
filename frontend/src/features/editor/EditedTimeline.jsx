import { useEffect, useRef, useState } from "react";
import useApi from "../../api/useApi";
import { formatTime } from "../../utils/time";
import Icon from "../../components/ui/Icon";
import { rulerTicks, timeToX, xToTime } from "./timelineMath";
import { useAIFilm, useVideoFrames } from "./aiFilm";
import "./Timeline.css";

const pct = (t, duration) => `${timeToX(t, duration, 100)}%`;

function Row({ kind, label, icon, onOpen, children }) {
  const name = <><Icon name={icon} size={16} /><span>{label}</span></>;
  return (
    <div className={`timeline-row timeline-row-${kind}`}>
      {onOpen ? <button type="button" className="timeline-label" onClick={onOpen} title={`Open ${label}`}>{name}</button>
        : <div className="timeline-label">{name}</div>}
      {children}
    </div>
  );
}

// The timeline for a finished AI edit: its own film (e.g. 13 s), not the 1:40 source it was cut from.
// Captions and B-roll come from the edit's beats; the video row shows frames of the edited film itself.
function EditedTimeline({ projectId, clip, state, plan, player, onOpenTool }) {
  const api = useApi();
  const duration = state.ai_edit.duration || plan?.total_duration || 1;
  const film = useAIFilm(api, projectId, clip, state);
  const frames = useVideoFrames(film, 12);
  const playheadRef = useRef(null);
  const laneRef = useRef(null);
  const [hover, setHover] = useState(null);

  // Beats sit back to back in the film, in plan order
  const beats = [];
  let at = 0;
  for (const beat of plan?.beats ?? []) {
    const length = Math.max(0, (beat.end ?? 0) - (beat.start ?? 0));
    beats.push({ ...beat, at, length });
    at += length;
  }
  const scale = at > 0 ? duration / at : 1;   // fit the beats to the film's real length
  const placed = beats.map((beat) => ({ ...beat, at: beat.at * scale, length: beat.length * scale }));
  const broll = placed.filter((beat) => beat.broll_query);

  useEffect(() => {
    let frame;
    const tick = () => {
      const t = player.current?.getTime() ?? 0;
      if (playheadRef.current) playheadRef.current.style.left = pct(Math.min(t, duration), duration);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [player, duration]);

  const jump = (event) => {
    const box = event.currentTarget.getBoundingClientRect();
    player.current?.seek(xToTime(event.clientX - box.left, duration, box.width));
  };
  const label = (t) => (duration < 20 ? `${Math.round(t)}s` : formatTime(t));
  const blocks = (items, text, kind) => items.map((beat) => (
    <button key={`${kind}-${beat.id}`} type="button" className={kind === "cap" ? "timeline-cue" : "timeline-block"} title={beat.spoken_text || text(beat)}
      style={{ left: pct(beat.at, duration), width: pct(beat.length, duration) }}
      onClick={() => player.current?.seek(beat.at)}>{text(beat)}</button>
  ));

  return (
    <div className="timeline timeline-edited">
      <div className="timeline-row">
        <span />
        <div className="timeline-ruler" title="Click to move the playhead" onClick={jump}>
          {rulerTicks(duration).map((t) => <span key={t} className="timeline-tick" style={{ left: pct(t, duration) }}>{label(t)}</span>)}
        </div>
      </div>
      <div className="timeline-tracks">
        <Row kind="captions" label="Captions" icon="captions" onOpen={() => onOpenTool?.("Captions")}>
          <div className="timeline-lane timeline-cues">
            {placed.length ? blocks(placed, (beat) => beat.emphasis_text || beat.spoken_text?.split(" ").slice(0, 3).join(" "), "cap")
              : <span className="timeline-no-cues">Captions are part of the edited video</span>}
          </div>
        </Row>
        <Row kind="broll" label="B-roll" icon="film" onOpen={() => onOpenTool?.("B-roll")}>
          <div className="timeline-lane">
            {broll.length ? blocks(broll, (beat) => beat.broll_query, "broll") : <span className="timeline-no-cues">No B-roll in this edit</span>}
          </div>
        </Row>
        <Row kind="video" label="Video" icon="play">
          <div ref={laneRef} className={`timeline-track${frames.list.length ? " has-filmstrip" : ""}`} onClick={jump}
            onMouseMove={(e) => { const box = e.currentTarget.getBoundingClientRect(); setHover(xToTime(e.clientX - box.left, duration, box.width)); }}
            onMouseLeave={() => setHover(null)} title={hover != null ? formatTime(hover) : undefined}>
            {frames.list.length > 0 && (
              <div className="timeline-filmstrip" aria-hidden="true">
                {frames.list.map((src, i) => <img key={i} src={src} alt="" draggable="false" />)}
              </div>
            )}
            <div className="timeline-kept" style={{ left: 0, right: 0 }} />
          </div>
        </Row>
        <Row kind="music" label="Music" icon="headphones" onOpen={() => onOpenTool?.("Music")}>
          <div className="timeline-lane">
            <button type="button" className="timeline-block" style={{ left: 0, width: "100%" }} onClick={() => player.current?.seek(0)}>Score</button>
          </div>
        </Row>
        <div className="timeline-playhead-layer">
          <div ref={playheadRef} className="timeline-playhead" />
        </div>
      </div>
      <div className="timeline-footer">
        <span>Edited video · 0:00 – {formatTime(duration)} · {formatTime(duration)} long</span>
        <span className="timeline-keys">Click to jump · ask the AI Editor to change the edit</span>
      </div>
    </div>
  );
}

export default EditedTimeline;
