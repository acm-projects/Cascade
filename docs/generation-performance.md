# Generation latency and long-source validation

Spoken documentary, history, news, interview and topic requests use a transcript-first
index. Explicit visual/action requests retain the multimodal index and frame inspection.
For up to 12 requested clips and a formatted transcript under 350,000 characters, the
configured AI provider receives the complete timestamped transcript in a batch selection
call, with at most one repair/refill call. This avoids both CLIP indexing and per-chunk
summaries/tool conversations for the common spoken-documentary path. Larger batches or
transcripts retain the existing summarized agent flow. Transcript-first mode still permits
real-frame inspection in that fallback flow; embedding search uses speech.

Multimodal indexing builds the transcript and visual indexes concurrently. Progress callbacks
run on the calling thread to preserve cancellation and job-state serialization. Existing
transcript, embedding and summary caches are retained.

Verified follow-up uploads reuse source bytes with a hard link when possible, falling back to
a copy across volumes or when hard links are unavailable. The original ownership checks run
before reuse. Clips become available as a stable, ordered prefix while later clips render;
the final results record is written only after completion. This preserves clip indexes.
`first_clip_ready_seconds`, `index_mode`, `index_timings` and `selection_mode` are recorded
with completed job results. Timings exclude browser upload time.

## Offline mechanics check

Run from the repository root:

```sh
python tests/manual/benchmark_long_video.py --fixture --output .test-tmp/long-video
```

This creates a low-resolution 2h10m, four-color video with an audio track and runs real
FFmpeg clip/caption rendering, local storage and result persistence. It verifies duration,
caption format and the actual frame color of clips from all four source chapters, including
a clip starting at 2:06:40. **AI selection is mocked. This is not evidence of documentary
semantic quality, real provider latency, or production-resolution encoding performance.**

## Live documentary check

After selecting an authorized source and approving provider use:

```sh
python tests/manual/benchmark_long_video.py --source documentary.mp4 --live --output .test-tmp/documentary
```

This uses configured Deepgram and AI services and can incur charges. The source must be at
least two hours long. Keep the resulting benchmark JSON and generated clips private. Review
the actual clips for relevance and natural boundaries; automated timestamp checks cannot
establish semantic quality. Initial upload, transcription and encoding still take time;
no instantaneous processing guarantee is implied.

## Research integration

`backend/agent/` selects clips. `backend/trends/` and `backend/integration.py:research`
compare an upload against trending YouTube videos as a separate research operation. They
share transcription/provider infrastructure; trend research is not run for ordinary clipping.
`backend/agent/research.py` stores clip-run findings and is not the trends research engine.
