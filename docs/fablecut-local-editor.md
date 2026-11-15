# Local FableCut sequence editing in Cascade

This integration uses the real FableCut 1.18.0 compositor, pinned to commit `579b08ec1a789baec5cbf06d7430373460508d09`. It is not ChatCut or Rendley, and it does not call a paid editing API. The local vision model interprets instructions; FableCut executes the resulting cuts, transitions, keyframes, text and final audio mix.

## Start from the Cascade repository root

```sh
python3 scripts/install_fablecut.py
```

This installs only the audited MIT source and its asset/license notices into the ignored `backend/editor/.cache/fablecut` directory. It does not run npm installation scripts, download AI models, or overwrite a different existing installation. Node 18+, Chrome/Chromium and FFmpeg must be installed. Chrome is detected at its usual macOS path; `FABLECUT_CHROME` can select another compatible executable.

Start Ollama if it is not already running, then install the free sequence model once:

```sh
ollama serve
```

In a separate terminal (the download is about 7.6 GB for the current default Mac runtime):

```sh
ollama pull qwen3.5:9b
```

Start the backend:

```sh
CASCADE_EDITOR_PROVIDER=ollama CASCADE_EDITOR_SEQUENCE_MODEL=qwen3.5:9b .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Start the frontend in another terminal:

```sh
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173`, sign in through Cascade's existing authentication, select a saved video in the editor and use **AI Editor → Create a high-energy Reel**. Existing `.env` credentials/configuration remain in place; this task does not rewrite them. The generic editor tools retain their existing small local model configuration. No model is automatically downloaded by chat and there is no paid fallback.

## What is connected

- Selected footage is analyzed through bounded local frame samples, scene boundaries and existing transcript cues. Available music is measured locally. Model output selects valid source candidates, bounded effect settings and a permitted local music asset.
- A FableCut sequence is part of the same saved `Edit` document as manual edits. The ordinary manual render is prepared first, then the sequence compositor reorders its ranges. Existing B-roll, motion, color and overlays remain in the underlying edit. Caption styling and manual audio are remapped onto the final sequence clock.
- Sequence cards expose source ranges, editable transitions and punch-ins, ordering, deletion and removal of the whole sequence. The compact sequence strip uses edited time; the existing footage ruler deliberately remains in source time. Seeking uses the source↔edited mapping, including linear speed integration.
- Manual and AI edits use shared Undo/Redo and autosave. In-session chat undo refuses to erase later manual changes. Undo history resets after page reload; the edit and conversation remain saved.
- FableCut runs in an isolated temporary data directory, binds only to loopback, and receives an allowlisted environment without Cascade service keys or database URLs. Existing owner/authentication checks protect media and draft access. It does not receive model-authored JavaScript, arbitrary media URLs or paths.
- Preview and export call the same rendering route. Successful sequence renders are cached by state, media metadata and renderer-source version; failed jobs do not become playable results. Job acceptance is not treated as completed rendering. Logs contain bounded stage/reason codes, not media, captions or credentials.

## Free components and boundaries

FableCut source is MIT ([license](https://github.com/ronak-create/FableCut/blob/main/LICENSE)); Qwen3.5 9B weights are Apache-2.0 ([model card](https://huggingface.co/Qwen/Qwen3.5-9B)). Inference runs locally through Ollama, with no request credits, subscription or card. Existing FFmpeg build licensing still applies. Asset/font license notices are retained. The soundtrack, impact, whoosh and riser used by this integration are Cascade procedural synthesis rather than downloaded commercial sound packs. Source-media rights remain those of the selected footage.

Inspected machine: Apple M4 Pro, 24 GB unified memory, macOS 26.6.2; about 47% system memory was available before evaluation. Model weights are not total runtime memory. Rendering is serialized to limit competing browser/FFmpeg jobs.

## Honest limitations

- Sparse images and scene detection are not continuous action understanding. Candidate reasons are model intent, not proof of what rendered.
- Captions use the existing VTT cue intervals; word grouping is estimated, not forced alignment. Incorrect source transcript text/timing remains a limitation.
- Source speed ramps do not use optical flow. Ramped production audio is muted, while dialogue candidates remain at normal speed and music/SFX use edited time. This avoids pitch-warping speech but is not sophisticated source-sound reconstruction.
- Portrait output is a centered crop, not tracked subject framing; some action or baked-in graphics can be cropped. Existing manual framing still applies to the underlying render.
- No automatic subject cutouts, rotoscoping, generative footage/music, freeze/reverse or advanced motion-tracked graphics are claimed by this adapter.
- Beat snapping is limited by safe source intervals and complete speech. Not every cut can land on a beat without damaging dialogue. Model omission or invalid settings must be reported rather than described as successful effects.
- This is an experimental local editing workflow, not a guarantee of professional editorial quality or a match to a supplied reference.

## Recovery and verification artifacts

The pre-change editor/source snapshot, tracked diff and Git status are preserved under `.test-tmp/editor-recovery-before-fablecut/`. Existing project media and original drafts were not overwritten during evaluation. Do not blindly extract the archive over newer work; compare the snapshot/diff first.

Evaluation uses a disposable copy of a real 38.038-second saved clip. Reference videos were downloaded only as local viewing copies and were not included in exported media. Sampled frames and scene-difference boundaries were inspected; this does not establish exact reference matching. Full render verification and final before/after artifacts are recorded separately with the sample.

## Actual evaluation result (31 October 2026)

FableCut passed the isolated real-media execution test, so a second engine was not needed. The first 4B planner trials failed the quality gate: some replies described effects without selecting executable settings. Required settings and the larger local Qwen3.5 9B model produced a valid sequence, and receipts now describe compiled settings rather than model prose.

On this M4 Pro/24 GB Mac, Ollama used its MLX runner with an 8192-token context and about 8 GB reported model memory. The initial local request took 58.9 seconds and the 20-second render took 15.6 seconds. A real conversational pacing revision took 57.5 seconds and rendered in 13.6 seconds. These are single-machine observations, not performance guarantees.

The 38.038-second source copy became a 9-second 540×960 MP4 with eight ordered shots: a complete two-second spoken hook followed by approximately one-second action shots, whip and blur transitions, one 1.5×→0.5× linear ramp, pop captions, a mild consistent contrast/saturation adjustment, a procedural music bed, selective whooshes and a riser. The revision also removed the initial small punch-in and retained one short shake. This shows a remaining limitation: broad model revisions can change creative settings beyond the requested pacing. Direct commands such as “Less shake” and “Move that zoom earlier by 0.1 seconds” revise existing parameters deterministically.

Decoded frame comparisons matched the planned source ranges, including the ramp, within one 30-fps frame in the sampled windows. Normal-speed audio cross-correlation measured about 5 ms lag; video/audio track ends differed by 19 ms. Cut boundaries were within 3.1 ms of the measured soundtrack onset grid before frame quantization. This is estimated onset analysis, not human-verified beat annotation. Save/reload retained the exact state, and repeated preview/export requests returned byte-identical MP4s. Browser checks confirmed sequence controls, rendered preview, original/edited comparison, manual deletion and undo/redo. A final UI “Less shake” request updated the existing edit and autosaved; “Undo your last edit” restored it with Redo available. Detailed shot controls are collapsed initially and the AI sequence layout reserves a usable preview height. Automated regression checks passed 81 backend tests and 78 frontend tests; the frontend production build and focused lint completed (one existing player effect warning and the large-bundle warning remain). These checks establish functioning execution, not professional aesthetic quality.

Playable local artifacts are under `.test-tmp/fablecut-evaluation/`: `comparison.html`, `before.mp4`, `after.mp4`, the initial edit where retained, actual plan/receipt JSON, sampled frame sheets, and audio/frame/beat verification records. All are ignored runtime artifacts, not committed media. The source/recovery snapshot remains separate.

Compared with the supplied references, the result still lacks sophisticated action-aware reframing, optical-flow slow motion, precise word alignment, curated commercial-quality sound design, tracked compositing, and a strong model guarantee of editorial continuity. The source already contains action and production sound; this integration did not create those. Center cropping visibly loses some wide-shot context. No reference matching or professional-quality claim is made. It is a working free local editing workflow with a real compositor, and further creative refinement is needed.
