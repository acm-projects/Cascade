import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import ClipNode from "./ClipNode";
import PromptNode from "./PromptNode";
import SourceNode from "./SourceNode";

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const mount = (node) => render(<ReactFlowProvider>{node}</ReactFlowProvider>);

describe("full prompt cards", () => {
  const data = { prompt: "Find funny moments", state: "done", clipCount: 2, referenceNumbers: [2, 4] };
  it("shows prompt, clip count, references and state without hovering or clicking", () => {
    mount(<PromptNode data={data} />);
    expect(screen.getByText("References: #2, #4")).toBeTruthy();
    expect(screen.getByText("Find funny moments")).toBeTruthy();
    expect(screen.getByText("2 clips · done")).toBeTruthy();
    expect(screen.queryByRole("button", { expanded: false })).toBeNull();
  });
  it("retains visible retry, stop and reuse callbacks for the appropriate state", () => {
    const onRetry = vi.fn();
    const onStop = vi.fn();
    const onReuse = vi.fn();
    const { rerender } = mount(<PromptNode data={{ ...data, state: "error", jobId: "job", onRetry, onReuse }} />);
    fireEvent.click(screen.getByText("Retry"));
    expect(onRetry).toHaveBeenCalledWith("job");
    fireEvent.click(screen.getByText("Reuse prompt"));
    expect(onReuse).toHaveBeenCalledWith(data.prompt);
    rerender(<ReactFlowProvider><PromptNode data={{ ...data, state: "processing", jobId: "job", onStop, message: "Finding candidate moments…" }} /></ReactFlowProvider>);
    expect(screen.getByText("Finding candidate moments…")).toBeTruthy();
    expect(screen.queryByText("Retry")).toBeNull();
    fireEvent.click(screen.getByText("Stop"));
    expect(onStop).toHaveBeenCalledWith("job");
  });
});

describe("clip interactions", () => {
  let play;
  let pause;
  beforeEach(() => {
    play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  });
  const base = { jobId: "job", clipIndex: 2, title: "The reaction", start: 41, end: 72, clipUrl: "/clip.mp4" };
  it("checkbox toggles without opening the card; the card opens the matching clip", () => {
    const onOpen = vi.fn();
    const onToggleSelect = vi.fn();
    mount(<ClipNode data={{ ...base, onOpen, onToggleSelect, selectionNumber: 3 }} />);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(onToggleSelect).toHaveBeenCalledWith("job", 2);
    expect(onOpen).not.toHaveBeenCalled();
    expect(screen.getByText("✓ Selected 3")).toBeTruthy();
    fireEvent.click(screen.getByText("The reaction"));
    expect(onOpen).toHaveBeenCalledWith("job", 2);
  });
  it("plays on hover and pauses and resets when leaving", () => {
    const { container } = mount(<ClipNode data={base} />);
    const video = container.querySelector("video");
    fireEvent.mouseEnter(video.parentElement);
    expect(play).toHaveBeenCalled();
    video.currentTime = 8;
    fireEvent.mouseLeave(video.parentElement);
    expect(pause).toHaveBeenCalled();
    expect(video.currentTime).toBe(0);
  });
  it("loads protected previews lazily and revokes their URL on leave", async () => {
    const createObjectURL = vi.fn(() => "blob:preview");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const loadPreview = vi.fn().mockResolvedValue(new Blob(["video"]));
    const { container } = mount(<ClipNode data={{ ...base, loadPreview }} />);
    const video = container.querySelector("video");
    expect(loadPreview).not.toHaveBeenCalled();
    fireEvent.mouseEnter(video.parentElement);
    await waitFor(() => expect(video.getAttribute("src")).toBe("blob:preview"));
    expect(loadPreview).toHaveBeenCalledWith("/clip.mp4");
    fireEvent.mouseLeave(video.parentElement);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:preview");
  });
  it("ignores a preview that finishes after unmounting", async () => {
    const createObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL: vi.fn() });
    let finish;
    const loadPreview = vi.fn(() => new Promise((resolve) => { finish = resolve; }));
    const { container, unmount } = mount(<ClipNode data={{ ...base, loadPreview }} />);
    fireEvent.mouseEnter(container.querySelector("video").parentElement);
    await waitFor(() => expect(loadPreview).toHaveBeenCalled());
    unmount();
    finish(new Blob(["video"]));
    await Promise.resolve();
    expect(createObjectURL).not.toHaveBeenCalled();
  });
  it("renders grade only when supplied and handles a missing preview", () => {
    const { rerender } = mount(<ClipNode data={{ ...base, clipUrl: null }} />);
    expect(screen.queryByLabelText(/Grade/)).toBeNull();
    rerender(<ReactFlowProvider><ClipNode data={{ ...base, grade: { letter: "A", score: 88 } }} /></ReactFlowProvider>);
    expect(screen.getByLabelText("Grade A, score 88")).toBeTruthy();
  });
});

describe("source contract", () => {
  it("accepts the ticket fields without requiring a studio session", () => {
    mount(<SourceNode data={{ title: "Interview", durationSeconds: 125, status: "ready" }} />);
    expect(screen.getByText("Interview")).toBeTruthy();
    expect(screen.getByText("2:05")).toBeTruthy();
  });
  it("announces preparing and error states", () => {
    const { rerender } = mount(<SourceNode data={{ status: "processing" }} />);
    expect(screen.getByText("Preparing video…")).toBeTruthy();
    rerender(<ReactFlowProvider><SourceNode data={{ status: "error" }} /></ReactFlowProvider>);
    expect(screen.getByRole("alert")).toBeTruthy();
  });
});
