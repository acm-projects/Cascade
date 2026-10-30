# CAS-12 verification

Completed October 29, 2026.

## Change

Moved `clerk_profile`, `clerk_configuration`, `authorized_parties`, `clerk_jwks`, `verify_clerk_token`, local dev-auth constants and checks, and the protected-path list into `backend/core/auth.py`. The middleware is now `authenticate_request`, registered by `app.middleware("http")(authenticate_request)` in `app1.py`. The startup dev-mode warning also lives in auth.

Auth/session/logout routes remain in `app1.py` and delegate to auth. Explicit re-exports preserve existing imports. Storage now calls `auth.clerk_profile` directly, removing the deferred dependency on `app1`. Unit tests and browser fixtures patch the moved dependencies in auth. Existing unrelated editor changes were preserved, with only auth patch targets adjusted where needed.

## Verification

- Full suite before: **264 tests, 263 passed, one failure**.
- Full suite after: **264 tests, 263 passed, the same one failure**.
- The unchanged failure is `test_editor_routes.EditorRouteTests.test_all_routes_match_pre_refactor_snapshot`: unrelated uncommitted advanced editor work adds three routes.
- Dedicated dev-auth suite: **9/9 passed**; logout suite: **1/1 passed**. Includes local/remote peer behavior, spoofed headers, supplied credentials, origin checks, identity preservation, startup warnings, and cookie cleanup.
- AST comparison confirmed all seven moved functions retain their exact logic; only the middleware name and decorator registration changed.
- `git diff --check` passed.

## Live HTTP and browser check

Started isolated local servers with real auth middleware, local metadata and temporary job directories. No auth functions were mocked. With dev auth enabled, `/api/projects` returned **200**, `/api/session` returned **200** with `{"user_id":"dev-user","dev":true}`, `/api/auth-config` returned dev-mode configuration, and project creation returned **201**. An untrusted origin returned **403**, and an empty Authorization header returned **401**.

With dev auth disabled, unauthenticated `/api/projects` returned **401**, `{"detail":"Please sign in first."}`. Verified both the live session and rejected projects request in the browser as well. Verification servers were stopped afterward. Existing credentials, Clerk configuration and user data were not changed.
