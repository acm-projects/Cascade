import { useState, useRef } from "react";
import { Link } from "react-router-dom";
import "./DrawingPage.css";
import drawingBg from "../assets/drawing-bg.png";
import bigPad from "../assets/lilypad-big.png";
import smallPad from "../assets/lilypad-small.png";

// Turn seconds into "m:ss", e.g. 75 -> "1:15"
function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// FAKE results for now: pick a few random moments from the video.
// Later, the backend will send back real { start, end } times instead.
function makeFakeSubclips(duration) {
  const count = 3 + Math.floor(Math.random() * 3);          // 3 to 5 subclips
  const clips = [];
  for (let i = 0; i < count; i++) {
    const length = Math.min(2 + Math.random() * 4, duration); // 2 to 6 seconds long
    const start = Math.random() * (duration - length);
    clips.push({ id: i, start: start, end: start + length });
  }
  return clips.sort((a, b) => a.start - b.start);            // in order through the video
}

// One small lily pad showing one subclip. Hover to play it.
function SubclipPad({ videoUrl, start, end }) {
  const videoRef = useRef(null);

  function jumpToStart() {
    videoRef.current.currentTime = start;
  }

  function loopWithinClip() {
    if (videoRef.current.currentTime >= end) jumpToStart();
  }

  function startPreview() {
    videoRef.current.play();
  }

  function stopPreview() {
    videoRef.current.pause();
    jumpToStart();
  }

  return (
    <div className="subclip">
      <div
        className="subclip-pad"
        style={{ backgroundImage: `url(${smallPad})` }}
        onMouseEnter={startPreview}
        onMouseLeave={stopPreview}
      >
        <video
          ref={videoRef}
          className="subclip-video"
          src={videoUrl}
          muted
          playsInline
          onLoadedMetadata={jumpToStart}
          onTimeUpdate={loopWithinClip}
        />
      </div>
      <span className="subclip-time">
        {formatTime(start)} – {formatTime(end)}
      </span>
    </div>
  );
}

function DrawingPage() {
  const [mainVideo, setMainVideo] = useState(null);       // { name, url, duration }
  const [isDragging, setIsDragging] = useState(false);
  const [messages, setMessages] = useState([]);           // [{ role, text }, ...]
  const [text, setText] = useState("");
  const [subclips, setSubclips] = useState([]);           // [{ id, start, end }, ...]
  const [isGenerating, setIsGenerating] = useState(false); // show the loading animation?

  // Load a video file into the big lily pad
  function loadVideo(file) {
    if (!file || !file.type.startsWith("video/")) return;
    if (mainVideo) URL.revokeObjectURL(mainVideo.url);
    setMainVideo({ name: file.name, url: URL.createObjectURL(file), duration: 0 });
    setSubclips([]);                                       // new video = old results no longer apply
    setMessages([
      ...messages,
      { role: "assistant", text: `Got ${file.name}! Tell me what to look for.` },
    ]);
  }

  // Once the browser has read the video, remember how long it is
  function handleVideoLoaded(e) {
    const duration = e.target.duration;
    setMainVideo((current) => ({ ...current, duration: duration }));
  }

  function removeVideo() {
    URL.revokeObjectURL(mainVideo.url);
    setMainVideo(null);
    setSubclips([]);
  }

  // --- Drag and drop on the big lily pad ---
  function handleDragOver(e) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave() {
    setIsDragging(false);
  }

  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);
    loadVideo(e.dataTransfer.files[0]);
  }

  // --- Chat ---
  function handleSend(e) {
    e.preventDefault();
    if (text.trim() === "" || isGenerating) return;

    const userMessage = { role: "user", text: text };

    if (!mainVideo) {
      setMessages([
        ...messages,
        userMessage,
        { role: "assistant", text: "Drop a video on the big lily pad first, then tell me what to find!" },
      ]);
      setText("");
      return;
    }

    setMessages([
      ...messages,
      userMessage,
      { role: "assistant", text: `Looking through ${mainVideo.name} for: "${text}"...` },
    ]);
    setText("");
    setSubclips([]);
    setIsGenerating(true);

    // Pretend the AI takes 2 seconds to search
    setTimeout(() => {
      const results = makeFakeSubclips(mainVideo.duration);
      setSubclips(results);
      setIsGenerating(false);
      setMessages((current) => [
        ...current,
        { role: "assistant", text: `Found ${results.length} moments! Hover a lily pad to preview.` },
      ]);
    }, 2000);
  }

  return (
    <div
      className="drawing-page"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => e.preventDefault()}
    >
      <form
        className="drawing-stage"
        style={{ backgroundImage: `url(${drawingBg})` }}
        onSubmit={handleSend}
      >
        {/* Big lily pad: drop or click to add the main video */}
        <label
          className={isDragging ? "big-pad dragging" : "big-pad"}
          style={{ backgroundImage: `url(${bigPad})` }}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <input
            type="file"
            accept="video/*"
            hidden
            onChange={(e) => loadVideo(e.target.files[0])}
          />

          {mainVideo ? (
            <video
              className="big-pad-video"
              src={mainVideo.url}
              autoPlay
              muted
              loop
              playsInline
              onLoadedMetadata={handleVideoLoaded}
            />
          ) : (
            <span className="big-pad-hint">Drop your video here</span>
          )}
        </label>

        {/* Subclip results: small lily pads on a stem */}
        <div className="subclip-area">
          {isGenerating && <p className="subclip-loading">🌊 Searching your video...</p>}

          {subclips.length > 0 && (
            <div className="subclip-list">
              {subclips.map((clip) => (
                <SubclipPad
                  key={clip.id}
                  videoUrl={mainVideo.url}
                  start={clip.start}
                  end={clip.end}
                />
              ))}
            </div>
          )}
        </div>

        <Link to="/editor" className="drawing-title">Continue to Editor</Link>

        <div className="chat-messages">
          {messages.map((message, index) => (
            <p key={index} className={`chat-message ${message.role}`}>
              {message.text}
            </p>
          ))}
        </div>

        {mainVideo && (
          <div className="chat-video-tag">
            <span>🎬 {mainVideo.name}</span>
            <button type="button" onClick={removeVideo} title="Remove video">✕</button>
          </div>
        )}

        <input
          className="chat-input"
          placeholder={mainVideo ? "What should I find in this video?" : "Drop a video first..."}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />

        <label className="chat-attach" title="Attach a video">
          <input type="file" accept="video/*" hidden onChange={(e) => loadVideo(e.target.files[0])} />
        </label>

        <button type="submit" className="chat-send" title="Send" />
      </form>
    </div>
  );
}

export default DrawingPage;