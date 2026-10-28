# LinkedIn personal-profile video posting

Cascade supports immediate public video posts to the connected member’s personal profile. Connecting LinkedIn is separate from signing in to Cascade. There is no company Page posting and no LinkedIn scheduling. No real post should be made during setup/testing without the user's explicit instruction.

## Developer app and access

1. Create/select a LinkedIn developer app. LinkedIn may require associating/verifying a company Page for the developer app; that does **not** authorize Cascade to post to that Page.
2. Add **Share on LinkedIn** under Products. Its posting permission is `w_member_social`, as documented in [Share on LinkedIn](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin).
3. Add **Sign In with LinkedIn using OpenID Connect** for `openid` and `profile`. Cascade requests `openid profile w_member_social`; email is not needed. It uses the authenticated [userinfo endpoint](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2) to get the member subject and profile name, and derives `urn:li:person:{sub}`. It does not trust an author supplied by the frontend.
4. Verify the scopes are listed in the app's Auth tab and grant them when connecting. Self-service scope provisioning is described in [Getting Access](https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access). A scope or successful OAuth connection does not prove that your actual app/token can call the versioned Videos and Posts endpoints. If LinkedIn rejects an endpoint, Cascade shows the failing stage, HTTP status and numeric service error code; check the app's enabled products/API entitlements in the Developer Portal and contact LinkedIn support if needed. It does not simulate a successful connection, upload or post, or assume Page permissions from personal permissions.
5. Company posting would require separate `w_organization_social` access, organization author selection, role checks and applicable approval. None of those are requested or implemented here.

## Configuration and exact callback

Set these in your private backend `.env` or deployment secrets:

```dotenv
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
LINKEDIN_REDIRECT_URI=https://localhost:8443/api/social/linkedin/callback
LINKEDIN_API_VERSION=202607
```

Register **exactly** `https://localhost:8443/api/social/linkedin/callback` in the app's Auth → Authorized redirect URLs for local development. LinkedIn documents an absolute HTTPS redirect URI in its [OAuth authorization-code flow](https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow). The configured Caddy proxy on 8443 forwards to FastAPI on 8000; see [local-https.md](local-https.md) for certificate trust and exact commands to start both services. Plain Uvicorn on 8000 does not provide HTTPS. Alternatively use your HTTPS backend origin plus `/api/social/linkedin/callback`, registering that exact URL and using it in `LINKEDIN_REDIRECT_URI`. Do not add query parameters or fragments.

Reuse the server-only `SOCIAL_TOKEN_ENCRYPTION_KEY` and `SOCIAL_DATABASE_PATH` configuration already used for social storage. Tokens and profile identity are encrypted with Fernet in user-scoped records in the private SQLite database. Retain the encryption key across restarts, back it up separately, and keep the database outside static/public directories. Database mode is 0600; the default `video_jobs/` path is ignored by Git. No Google credentials are required to use LinkedIn. Never put client secrets or tokens in frontend code or Git. Existing connections expire at the lifetime LinkedIn returns; reconnect on expiry/revocation. Programmatic refresh tokens are partner-restricted, so Cascade does not assume they are available.

`202607` is the version used against the currently documented Videos API. Monitor LinkedIn's version migrations/sunsets and set a supported `YYYYMM` version for your app. Do not silently fall back to deprecated API versions or the old Assets/ugcPosts APIs.

## Publication protocol

The panel retains the existing selected clip's edited preview, title, caption and hashtags. LinkedIn shows Connect LinkedIn, connected personal profile identity, explicit Publish to LinkedIn, progress, errors and View on LinkedIn after confirmed creation. It clearly says that this is a public personal-profile post.

Only the explicit Publish request saves an immutable snapshot of edits and post copy and starts the worker. It reuses the existing final MP4 export callable, including subtitle overlays, reframing, B-roll and other saved edits. LinkedIn captions refer to post commentary; video subtitles are already rendered into the exported MP4. No separate subtitle track or selected cover frame is uploaded to LinkedIn in this implementation.

The backend follows the supported [Videos API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/videos-api?view=li-lms-2026-07): initialize upload with the connected person as owner, upload the exact instructed byte ranges, collect ordered ETag part IDs, finalize, and wait for `AVAILABLE`. It verifies the returned video's owner. Processing failures never create a post. Cascade conservatively accepts clips of 3 seconds–30 minutes and final files of 75 KB–500 MB; LinkedIn may apply additional requirements.

The [Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api?view=li-lms-2026-10) receives the person author, video URN, title and caption/hashtags, `visibility: PUBLIC`, main-feed distribution and `lifecycleState: PUBLISHED`. Caption reserved characters and validated hashtag templates use LinkedIn's [little text format](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/little-text-format). Only HTTP 201 with a valid `x-restli-id` yields Published and a feed post link. This acknowledges API creation; it does not imply independent human inspection of the live post. `r_member_social` is restricted and is not requested merely to read back a post.

The persistent key is Cascade user/project/job/clip, separate from YouTube records. File locks serialize submissions and post creation on one host. The snapshot binds the connected person; reconnecting another profile cannot redirect an existing job. Duplicate submissions, reopen and refresh reuse existing records. A post-attempt marker is saved **before** sending the create-post request. Ambiguous failures block retries and tell the user to inspect their LinkedIn profile; no automatic duplicate post retry occurs. Failed pre-upload requests can be retried explicitly. An existing video URN is retained rather than uploading again. Interrupted jobs are surfaced as failures rather than resumed automatically; inspect the profile before recovery. This is single-host persistence, consistent with the existing social storage implementation, not a distributed job queue.

GET status never creates a post. The worker completes only a previously saved explicit publish request, even if the panel closes. OAuth callback state is random, short-lived and atomically single-use. Application logs omit raw provider error prose, access tokens, codes, secrets and signed upload URLs. The callback query is redacted from Uvicorn access logs; configure any reverse proxy's access logs to redact it too.

## Verification and remaining setup

```sh
python3 -m unittest tests.test_social_linkedin tests.test_social_youtube tests.test_youtube_schedule tests.test_editor -q
python3 tests/test_linkedin_browser.py
```

The LinkedIn browser suite uses `tests/editor_browser_server.py` on 8767 and isolated Chrome DevTools on 9334. All LinkedIn OAuth/post responses are mocked; it verifies the compact desktop/mobile interface, missing-config messages, popup blocking, explicit publish, correct current-clip snapshot, progress/result link, duplicate protection, reload persistence, access failures and preserved YouTube controls. Backend checks cover encryption, ownership, OAuth state replay/expiry, missing scopes, token expiry, multipart upload/finalization, renderer reuse, profile binding and post rejection. No real OAuth connection or live post was tested. Locally the LinkedIn client ID, client secret and redirect URI were absent during implementation; add them and enable the products above before live connection. API entitlement remains unverified until an authorized live attempt is made. Do not publish real content as a verification shortcut.
