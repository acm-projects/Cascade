# AI Editor: free/local options and implementation

Reviewed 2026-10-31 against maintainer documentation, model cards, repository licenses, research, and developer issue reports. This concerns the editor only; Studio, Trends, social integrations and their provider selection are unchanged.

## Recommendation for this Mac

Use the already-installed **Ollama `qwen3-vl:4b-instruct`**, a quantized ~3.3 GB Apache-2.0 vision-language model, with Cascade's existing FFmpeg/libass renderer, local onset/tempo measurements and procedural audio catalog. The inspected machine is Apple M4 Pro / 24 GB unified memory. Weight size is not runtime RAM: image tokens, KV cache, rendering, and other apps need additional memory. This is a practical small-model choice for this machine, not a claim that every larger model will fit. No model download, new paid service, or hosted account is required by this implementation. Inference speed/quality are bounded; this is not a professional human editor.

The original chat used the shared `LLM_PROVIDER` (configured as OpenAI on this installation), a wide structured action schema, transcript and scene-cut hints, but **no actual image input**. Most rendering primitives already existed. Missing update/remove tools, preset-like style execution, destructive clearing of manual tracks, and stale-response overwrites were integration problems a model swap alone could not fix.

## Comparison

| Option | Availability, license and cost | Understanding/planning | Execution and Cascade fit |
| --- | --- | --- | --- |
| Qwen3-VL 4B + local Ollama | Available model weights; Apache-2.0. Ollama MIT. Local inference has no hosted request quota or trial expiration. Existing download ~3.3 GB; compute/electricity are still local costs. | Image/video-capable model. Ollama's documented interface accepts images and schema-constrained JSON; this adapter sends a labeled sampled-frame contact sheet, transcript, current state, conversation and available audio. | No built-in editing/rendering engine. Cascade implements plan validation, cuts, effects, revisions and rendering. Recommended. |
| Qwen3.5 4B / MLX-VLM / llama.cpp | Qwen model card lists Apache-2.0; MLX-VLM and llama.cpp are MIT. Models and quantizations require separate downloads. MLX-VLM targets Apple Silicon; llama.cpp supports Metal. | Alternative local multimodal inference/planning. Model/quantization/runtime compatibility must be tested; newer model names alone do not establish better timeline plans. | No built-in timeline tools. Not downloaded or installed: the existing working runtime avoids an unnecessary migration and large download. |
| QCut | Maintainer repository describes MIT source, macOS builds and a structured CLI/agent plugins. Local editing/export are free; optional AI generation uses selected providers and can require keys or sign-in. | Agent host and tools, with inference/provider costs separate. | Real multi-track/video/audio/text/effect interfaces. An alternative editor, not a drop-in Cascade backend. Native tooling, state conversion and a second render pipeline would be substantial integration work. |
| OpenCut | MIT source. Maintainers identify an active rewrite and direct users to classic for current use. | New MCP/headless facilities are described in the rewrite; availability must not be confused with a completed, tested Cascade agent. | Useful source/API concepts, but replacing this UI/state/render path would conflict with the preservation scope. |
| Diffusion Studio Agent | MIT repository. Agent framework/source, not an unlimited free model service. | Plans/composites using an LLM; the model backend still needs local compute or an API. | Usable code-based editing framework; adapting it would introduce another composition system. Not necessary for effects Cascade already renders. |
| Gemini Developer API free tier | Actual API free tier for eligible models, distinct from a consumer editor website or trial credits. Requires a Google project/key and service terms. Quotas vary by model/project and are shown in AI Studio; no guaranteed RPM/day quota is assumed. Free-tier content may be used to improve Google products. | Strong hosted multimodal analysis and structured planning. | No native Cascade timeline execution. Not enabled: a new external service and privacy/account choices are unnecessary here. |
| Remotion / FFmpeg + local beat analysis | FFmpeg is LGPL/GPL depending on build/features (libx264 changes distribution obligations). Remotion is source-available with free-license eligibility/commercial company-license conditions, not universally MIT/free. | Neither is a conversational video-understanding model. Beat measurements are DSP, not language-model guesses. | Execution layer. Keep the existing FFmpeg pipeline rather than rewrite exports. No watermark filter is introduced by this implementation. Media/music rights remain separate from software licenses. |

No complete agent here automatically guarantees natural-language revisions, beat cuts, subject-aware zooms, transitions, animated captions, B-roll and music with no integration work. Research such as LAVE supports describing/understanding footage separately from executing bounded edits; it is research evidence, not a turnkey unlimited API.

## What is built in versus implemented here

- **Model/runtime:** sampled-image understanding, language interpretation, bounded structured plans. Model output cannot execute Python, shell, arbitrary paths, URLs or unregistered tools.
- **Cascade tools:** real source-time state changes; measured beat/onset alignment; phrase-safe pause cuts/ramps; timed punch-ins/shake; animated pop/karaoke captions; text overlays; audio beds/SFX, looping, fades and dialogue ducking; source/stock cutaways; entrance/exit fades and supported B-roll dissolves; Instagram 9:16 Fit framing.
- **Follow-ups:** motion update/remove tools target existing indices; common “less shake” and relative zoom-move requests have precise local revisions. Ambiguous references ask for a zoom number instead of selecting randomly. Chat undo uses the editor's shared in-session undo stack and does not erase newer manual changes.
- **Preservation:** AI-owned style segments are recorded so reapplication can replace those segments while preserving manual tracks and manually modified events. Newer manual changes made while inference runs cause the incoming plan to be rejected. Autosave and preview/export use the same edit model and renderer.
- **Truthfulness:** replies and execution receipts distinguish applied, preserved, skipped and failed operations. A timeline update is not a verified render. Preview errors remain visible. Beat cuts are not invented when there is no speech-safe interval. Sampled frames are not continuous action understanding; word highlights are estimated from transcript intervals.
- **Remaining unsupported:** generative footage/music, freeze frames, reverse, masks/rotoscoping, optical-flow slow motion, arbitrary inter-shot transition plugins and reliable word-level forced alignment. B-roll search needs the existing configured Pexels integration and downloadable licensed assets; the local model is not a free stock library. No external generation service is silently introduced.

## Configuration

The editor defaults to local inference, independently of `LLM_PROVIDER`:

```text
CASCADE_EDITOR_PROVIDER=ollama
CASCADE_EDITOR_OLLAMA_URL=http://127.0.0.1:11434
CASCADE_EDITOR_OLLAMA_MODEL=qwen3-vl:4b-instruct
```

These defaults are in source; `.env` is not rewritten. Only loopback inference URLs are accepted. The server never auto-pulls a model or falls back to a paid provider. If the installed model/server is unavailable, it returns an actionable error. Explicit existing `CASCADE_EDITOR_PROVIDER=openai` or `anthropic` retains the previous configured-cloud adapter; doing so uses that provider's credentials/pricing, not a free tier. The shared provider implementation is unchanged.

The contact sheet deliberately contains one labeled composite image: maintainer issue reports document adjacent same-size images being merged as temporal frames by some Qwen/Ollama runtimes. JSON is validated regardless of HTTP 200 or runtime grammar support. Long conversations are bounded to the latest 20 messages, and local output is bounded. No raw responses, frame data, credentials, or provider exception messages are written to logs.

## Verification on a real saved clip

Used an isolated copy of a real 38.038-second saved clip, its transcript and persisted edits. Original project/draft data was not modified. No live social publishing was performed. The actual installed Qwen model (no mocked inference) produced a validated plan in about 29 seconds end-to-end. The first broad tool schema proved unreliable on this small model; the high-energy path now uses a compact intent-specific schema and validates every response before execution.

The rendered 540×960 MP4 contains three content-anchored punch-ins/shakes, a measured-beat music bed, a whoosh, and pop captions. All three initial motion anchors were within 2 ms of measured music beats. Decoded audio cross-correlation measured 0 ms dialogue lag in three sampled windows (correlation 0.990–0.999) and 0 ms added-music lag (correlation 0.899). Video/audio endpoints differed by about one frame. Inspected actual output frames, including successive caption frames showing the pop animation. Preview and export use the same rendering pipeline and saved edit state.

This particular clip had no safe long dialogue pause for new source cuts or speed ramps; those were reported as skipped. The portrait result uses Fit with letterboxing, not subject-tracked cropping. Sparse frame selection can miss fast moments, and the local model does not deeply understand audio semantics: music selection uses available tags/tempo while beat timing is measured separately.

Native Chrome checks confirmed the AI Editor panel, actual high-energy request, timeline changes, rendered edited preview, direct shake reduction, moving an existing zoom, shared Undo/Redo, and save/reload of timeline and conversation. In-session AI undo history intentionally resets after reload. An immediate revision counter rejects stale plans even when manual state updates are still queued. Regression validation: 77 frontend tests, production build, targeted frontend lint and 75 backend tests passed (including editor rendering and YouTube/LinkedIn checks).

## Primary sources and developer discussions

- [Qwen3-VL 4B model card/license](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct) and [Ollama quantized model size](https://ollama.com/library/qwen3-vl:4b-instruct)
- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [chat API](https://docs.ollama.com/api/chat), [MIT license](https://github.com/ollama/ollama/blob/main/LICENSE)
- [Qwen3.5 4B model card](https://huggingface.co/Qwen/Qwen3.5-4B), [MLX-VLM](https://github.com/Blaizzy/mlx-vlm), [llama.cpp](https://github.com/ggml-org/llama.cpp)
- [QCut maintainer repository](https://github.com/Quriosity-agent/qcut), [OpenCut maintainer repository](https://github.com/OpenCut-app/OpenCut), [Diffusion Studio Agent](https://github.com/diffusionstudio/agent)
- [LAVE research paper](https://arxiv.org/abs/2402.10294)
- [Gemini API pricing/free-tier data handling](https://ai.google.dev/gemini-api/docs/pricing), [quota documentation](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Remotion current terms](https://www.remotion.dev/docs/terms), [FFmpeg licensing/build considerations](https://ffmpeg.org/legal.html)
- [Maintainer issue: adjacent images merged into video frames](https://github.com/ollama/ollama/issues/17321), [runtime-dependent structured-output issue](https://github.com/ollama/ollama/issues/17933), [Qwen image/context overflow report](https://github.com/ollama/ollama/issues/13084). These are reproducibility warnings from issue discussions, not guarantees that every installed version has those bugs.
