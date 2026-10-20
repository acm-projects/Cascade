# Pexels B-roll in the clip editor

Implemented on `manila/pexels-broll`. The editor’s **Download edited MP4** renders B-roll. The separate Exports page continues to download original generated media.

## Setup

Use the existing Python environment and FFmpeg/FFprobe installation. No additional Python dependencies are needed. Put `PEXELS_API_KEY` in the existing root `.env` (an empty placeholder is in `.env.example`), then restart the API:

```sh
python3 -m uvicorn app1:app --reload --host 127.0.0.1 --port 8000
```

The existing `load_dotenv(..., override=True)` in `app1.py` loads the key. Only the backend reads it, and only Pexels API calls receive the Authorization header. The browser requests authenticated Cascade endpoints; media-host requests carry no provider credentials. Do not print `.env`, enable HTTP header dumps, or put keys in URLs.

Chat still requires the existing server-side OpenAI configuration. Its model selection remains `OPENAI_EDITOR_MODEL` → `OPENAI_SCENE_MODEL` → `gpt-5.4-mini`.

## Complete example

1. Open a generated clip at least 10 seconds long and select **B-roll**.
2. Search for **mountain hiking**, preview a result, and check its creator/source link.
3. Set placement start to **4**, duration to **5**, source offset to **0**, framing to **Fill**, then choose **Add to clip**.
4. Scrub/play through seconds 4–9. Stock replaces the visible main video, its audio is muted, the speaker’s audio continues, and additional captions stay above it. At second 9 the main video returns.
5. Select the stock block on the timeline to change its numeric timing, replace it with a selected result, or remove it. Undo/redo includes B-roll edits.
6. Refresh or switch clips and return: the segments restore for that clip. Click **Download edited MP4** for the composited result.

Chat can search with “Find mountain hiking B-roll”, insert with “Add result 2 from second 4 to second 9”, and update/remove a selected timeline segment with “Move that B-roll to second 8”, “Shorten it to 3 seconds”, or “Remove that B-roll”. Search does not insert footage. Requests that cannot identify a displayed result or selected segment require clarification. Search result context is session-only; search again after refresh to insert another result.

All numeric controls and timeline timestamps use the full generated clip’s seconds. For chat, explicitly say “seconds into the trimmed preview” to use preview-relative placement; the backend adds the current trim start. Trimming only hides portions of stock segments; resetting trim recovers them. A partially visible segment advances its source offset by the hidden leading duration.

## Implementation and limits

- `backend/broll.py`: validated Pexels API mapping, clip-scoped registry, 24-hour search cache, bounded media download and FFprobe validation.
- `backend/editor_backend.py`: owner-checked search/thumbnail/media routes, draft validation, structured chat actions, FFmpeg composition.
- `web/editor_broll.js`: results, attribution, preview, numeric edits, selected-segment context, synchronized muted overlay.
- `web/editor_state.js`, `web/editor_timeline.js`: persisted segments, undo/redo, dedicated selectable stock track.

At most 30 nonoverlapping segments per clip. Fit or centered Fill are supported. Numeric placement/resizing is provided; timeline dragging/resizing of stock blocks is not implemented. Existing main-clip trim dragging is unchanged. Main audio is preserved; mixing stock audio, transitions, speed changes, and stock color correction are not supported. Burned-in original captions are part of the main video pixels and may be covered by stock; the editor’s additional caption layer stays on top.

The backend chooses an MP4 rendition near 1280px, never above 1920px on either axis. Downloads are limited to 100 MiB/video and 5 MiB/thumbnail, with a 1 GiB per-clip media cache cap; oversized/unsupported footage is rejected. Each clip’s registry retains at most 2,000 asset references, and caches at most 100 search pages with a 24-hour TTL. Downloaded assets remain in the clip-scoped server storage to support saved drafts and undo; there is no automatic eviction of these persistent media files. They are local server files, including when the generated clip is retrieved from S3; use durable server storage for drafts/assets.

Only exact HTTPS Pexels media hosts are fetched, using provider-returned URLs saved server-side. Redirects, arbitrary client/AI URLs, filesystem paths, and unknown or cross-clip asset IDs are rejected. Responses/errors never include the API key or raw provider errors. Deleted/revoked provider assets may require replacement if they have not already been cached.

## Verification

```sh
python3 -m unittest tests.test_frontend_routes tests.test_frontend_views tests.test_editor tests.test_broll -q
node tests/test_editor_state.cjs
node tests/test_editor_flow.cjs
```

The backend tests mock provider/AI calls; FFmpeg tests use real colored fixtures and distinct audio tones to verify insertion intervals, source offsets, multiple segments, trim intersections, captions above stock, and original audio preservation. The isolated browser server also uses temporary storage and mocked providers:

```sh
python3 tests/editor_browser_server.py
# In separate terminals: isolated Chrome with --remote-debugging-port=9333
# and --remote-allow-origins=http://localhost:9333, then run suites sequentially:
python3 -m tests.test_broll_browser
python3 tests/test_editor_browser.py
```

No paid OpenAI calls are needed for these tests.

## Official provider references

- [Pexels API documentation](https://www.pexels.com/api/documentation/): video search at `/v1/videos/search`, Authorization header, pagination, attribution, and default rate limits (200/hour, 20,000/month).
- [Pexels caching guidance](https://help.pexels.com/hc/en-us/articles/900006470063-What-steps-can-I-take-to-avoid-hitting-the-rate-limit): recommends caching responses for 24 hours.
- [Pexels license](https://www.pexels.com/license/), [Terms of Service](https://www.pexels.com/terms-of-service), and [API terms guidance](https://help.pexels.com/hc/en-us/articles/900005880463-What-are-the-Terms-and-Conditions): content use must comply with these terms, including restrictions on standalone redistribution. This feature incorporates footage into an edited clip, credits creators with source links, and links prominently to Pexels; it does not provide a standalone stock-download interface.
