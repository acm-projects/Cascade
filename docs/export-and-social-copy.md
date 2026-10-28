# Edited downloads and social copy

## Downloads (CAS-46)

Export → Download settings applies to the MP4 and selected ZIP buttons. Original,
1080p, and 720p cap the composed video's **short side**; smaller videos stay small.
Resolution is applied after composition, B-roll, effects, and captions so their
placement scales together. Turning captions off affects additional captions, not
text already burned into the uploaded footage. These choices never overwrite drafts.

Each download fetches the latest saved draft. A ZIP uses one batch request and
includes one MP4 per checked clip. Downloads show rendering status, prevent duplicate
requests while busy, offer retry after errors, and warn for batches over ten clips.
The app cannot report encoder percent from these synchronous endpoints; status is
an honest rendering message, not simulated progress.

## Social copy (CAS-47)

`POST /api/projects/{pid}/clips/{jid}/{index}/social-copy`

Body: `{"platforms":["youtube","tiktok","instagram","linkedin"],"vibe":"calm and educational"}`.
Select 1–4 platforms; vibe is optional and limited to 300 characters. The endpoint
is available in `/docs`; platform copy UI remains a separate feature.

One structured provider call uses the clip title, saved trim's transcript (including
edited caption text), original request, and saved user preferences. It preserves
attribution and uncertainty instead of inventing facts. Pydantic checks the shape;
code normalizes/deduplicates hashtags and enforces output budgets. Emoji lengths
are counted in UTF-16 units for conservative caption limits.

Owner-scoped `social_copy.json` metadata is stored next to that clip's draft,
using the existing local/Neon metadata store. Cache keys include platforms, vibe,
trim and relevant context; `?refresh=true` forces a new provider call. No social
posting or paid model calls happen in the automated tests.

Platform references checked October 28, 2026:

- [YouTube video resource](https://developers.google.com/youtube/data/reference/rest/v3/videos): title 100 characters; description 5000 bytes. We use short descriptions.
- [TikTok Direct Post](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post): caption 2200 UTF-16 units including hashtags.
- [LinkedIn posts](https://www.linkedin.com/help/lms/answer/a528176): post 3000 characters.
- [Meta media creation reference](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/): Instagram uses the ticket's conservative 2200-character/5-hashtag cap. Direct re-verification was rate-limited (HTTP 429).

Run `.venv/Scripts/python -m unittest tests.test_export_downloads tests.test_social_copy`
and `npm test` / `npm run build` from `frontend/`.
