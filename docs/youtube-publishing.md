# YouTube publishing setup

1. In Google Cloud, enable **YouTube Data API v3**. Configure the OAuth consent screen and add test users while in testing mode.
2. Create an OAuth **Web application** client. Register this exact local redirect URI: `http://localhost:8000/api/social/youtube/callback`. For deployment use your HTTPS backend URL with the same path. Set `GOOGLE_YOUTUBE_REDIRECT_URI` to the exact registered URI.
3. Fill `GOOGLE_YOUTUBE_CLIENT_ID` and `GOOGLE_YOUTUBE_CLIENT_SECRET` in the backend environment. Generate a Fernet key using the command in `.env.example` and set `SOCIAL_TOKEN_ENCRYPTION_KEY`. Keep this key stable and back it up separately from the database. Install the updated Python requirements.
4. Keep `SOCIAL_DATABASE_PATH` on persistent private backend storage, outside static directories. The default is ignored by Git. Tokens are encrypted; database permissions are 0600. Protect the containing directory and backups. This SQLite implementation supports workers on a single host; use shared database/job infrastructure before deploying across hosts.
5. Open a clip's Post panel, choose YouTube, click Connect YouTube, grant upload, read and video-management permissions, then return and click Refresh connection. This connection belongs to the signed-in Cascade user and is independent of Clerk sign-in. Download requires no Google connection.
6. Review title, description, hashtags and privacy (default Private), then explicitly click Publish. Previewing and connecting never upload. Instagram offers a manual Download & Open Instagram handoff; LinkedIn remains disabled. Timing is available only under YouTube: choose Post now or Schedule. Existing connections must reconnect once to grant video-management permission for scheduling.

Upload renders through the existing final export function, including saved edits, client-generated caption overlays, reframing and B-roll. Status is persisted through Rendering, Uploading, Processing and Published/Failed. Processing is checked against YouTube. The same submission or active/completed clip returns its existing upload instead of uploading twice, including after reopening the panel. A completed clip cannot be published a second time through this panel. Failures before any media upload allow an explicit retry. Once media transfer has started, ambiguous failures block new uploads; inspect YouTube Studio rather than retrying the upload. Existing video IDs are always reused for schedule management. Uploads are not automatically retried. Interrupted workers are detected by process liveness on this single host; process-ID reuse is a limitation of this lightweight worker implementation.

Google may require OAuth verification before production access. Scheduling and privacy restrictions are checked against the live API response and read-back; Cascade does not infer eligibility from OAuth success. Consult Google’s current videos.insert and videos.update documentation for project requirements. Consent-screen testing mode can also limit refresh-token lifetime. No API key or frontend Google secret is used for publishing.

Validation: `python3 -m unittest tests.test_social_youtube tests.test_editor -q` covers state replay/cancellation, ownership, encrypted credentials, idempotency, Private defaults, final-render reuse, upload failure and real FFmpeg downloads. `node tests/test_exports_selection.cjs` checks preserved selection behavior. Live OAuth, channel upload and remote processing require configured credentials and an authorized test channel.

## Diagnosing connection errors

Restart the backend after updating the callback, then start a **new** Connect YouTube attempt. OAuth state is single-use, including failed attempts; reloading the old callback cannot retry it.

The backend emits safe diagnostics such as:

```
YouTube OAuth token_exchange succeeded upload_scope=True readonly_scope=True refresh_token_present=True
YouTube OAuth failed diagnostic=<reference> step=channel_lookup http_status=403 reason=PERMISSION_DENIED,SERVICE_DISABLED
```

These are example diagnostics, not a record of a live failure. The callback page includes the failing step and the same diagnostic reference. Log fields contain fixed stage names, HTTP statuses, booleans and allowlisted provider reason codes. Raw Google responses, provider error descriptions, tokens, authorization codes, PKCE verifiers, OAuth state and secrets are excluded. Cascade also removes the callback query string from Uvicorn access logs. Configure reverse proxies or other access log collectors to redact this query string as well.

- `token_exchange`: Google rejected the code exchange. `invalid_client` points to client credentials; `invalid_grant` can indicate an expired/reused code, mismatched redirect URI or PKCE failure. Check server configuration against the registered OAuth web client.
- `scope_validation`: the token response lacks one or both required scopes; logs identify each scope's presence independently.
- `offline_access`: Google returned no refresh token. This is separate from a missing channel or missing scopes.
- `channel_lookup`: inspect the HTTP status and provider reason. `SERVICE_DISABLED` or `accessNotConfigured` means check YouTube Data API v3 in the OAuth client's Google Cloud project; `insufficientPermissions` means inspect granted permissions. `no_channel_returned` means the authenticated identity returned an empty channel list, which can differ from another channel under the same Google login or Brand Account.
- `credential_storage`: check database permissions and encryption configuration.

No failure cause can be recovered from the old generic callback message alone: the original callback discarded its exception without logging it. A fresh attempt with these diagnostics is required if no upstream logs were retained.


## Native YouTube scheduling

YouTube’s [video status documentation](https://developers.google.com/youtube/data/reference/rest/v3/videos#status.publishAt) requires `privacyStatus: private` for `publishAt`, permits scheduling only videos that have never been published, and warns that a past timestamp can publish immediately. [videos.update](https://developers.google.com/youtube/data/reference/rest/v3/videos/update) requires the `youtube.force-ssl` (or broader YouTube) scope; upload permission alone cannot change or cancel a schedule. Add the video-management scope to the Google consent-screen configuration and reconnect existing accounts. The redirect URI and environment configuration remain unchanged.

The calendar defaults to the browser’s IANA timezone, shows the chosen local time and timezone, and posts wall-clock date/time plus its selected UTC offset. The backend independently resolves this with Python `zoneinfo`, rejecting past/near-future times, nonexistent daylight-saving times and mismatched offsets. Repeated hours require an explicit first/second occurrence choice. The minimum buffer is 30 minutes at submission, after rendering and before arming the final native schedule; it is not an estimate or guarantee of processing duration.

At the explicit Schedule on YouTube click, Cascade snapshots the validated edits (including rendered subtitle overlays, framing and B-roll references), title, combined description/caption, hashtags, connected channel ID/name and requested timezone/time. This snapshot is backend-only. Rendering uses the existing final MP4 export function. For safety, the resumable upload starts Private **without arming publishAt**. The backend waits for successful processing, verifies the original connected channel, then calls `videos.update(part=status)` with `privacyStatus: private` and the future UTC `publishAt`. This two-phase approach deliberately avoids attaching a deadline to an unprocessed upload: if rendering/processing overruns the buffer, no publication is armed, the video stays Private, and the panel asks for a new time.

Cascade marks Scheduled only after processing succeeds and a subsequent `videos.list` confirms the exact timestamp and Private status. Once confirmed, **YouTube owns publication**; the browser and Cascade server can close before publication time. Until confirmation, the server must finish rendering/uploading/processing. Processing/confirmation jobs are persisted and resumed on backend startup; interrupted rendering/media transfer is surfaced without automatically duplicating an upload.

Change schedule updates the same video ID and validates the new time. Cancel schedule asks for explicit confirmation, updates that video to Private while omitting `publishAt`, then verifies that the schedule was removed. Other mutable status fields (audience, synthetic media, license, embedding and stats visibility) are preserved. Schedule management does not upload later edits to the form or render the video again.

The persistent job stores current schedule, IANA timezone, UTC timestamp, video ID, revision, state and original snapshot. Per-clip file locks serialize schedule mutations across processes on one host, with durable mutation intent before the Google call. Revision checks reject stale tabs. Ambiguous schedule-update responses are reconciled with a read-back, never with another upload. Rejected schedules surface the provider HTTP status and safe reason (for example `invalidPublishAt` or `insufficientPermissions`); an existing remote schedule may still be active until a successful change or cancellation. Inspect YouTube Studio when a change cannot be confirmed. A confirmed schedule can also be edited independently in YouTube Studio; Cascade detects changes on refresh.

Focused verification:

```sh
python3 -m unittest tests.test_youtube_schedule tests.test_social_youtube tests.test_editor -q
node tests/test_schedule_time.cjs
python3 tests/test_youtube_schedule_browser.py
python3 tests/test_exports_post_browser.py
```

The browser suites use the isolated `tests/editor_browser_server.py` fixture and Chrome DevTools on port 9333. Google transport is mocked; UI screenshots are `/tmp/cascade-schedule-desktop.png` and `/tmp/cascade-schedule-mobile.png`. These checks do not perform a real YouTube scheduled upload or establish a real project's/channel's scheduling eligibility.
