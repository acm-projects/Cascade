"""Public frontend pages and thin authentication/session routes."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from backend import frontend
from backend.core import auth, config, jobs as job_service

router = APIRouter()


def serve_new_page(filename):
    if filename not in config.FRONTEND_FILES:
        raise HTTPException(
            404,
            "Page not found.",
        )

    if filename in frontend.PAGES:
        from fastapi.responses import HTMLResponse
        return HTMLResponse(frontend.render_page(filename, config.FRONTEND_DIR), headers={'Cache-Control':'no-store'})

    path = config.FRONTEND_DIR / filename

    if not path.is_file():
        raise HTTPException(
            404,
            f"Frontend file {filename} is missing.",
        )

    return FileResponse(
        path,
        headers={
            "Cache-Control": "no-store",
        },
    )


@router.get("/")
def show_website():
    return serve_new_page("index_C.html")


@router.get("/login")
def login_page():
    return serve_new_page("login_C.html")


@router.get("/api/auth-config")
def frontend_auth_config(request: Request):
    dev_auth = auth.is_dev_auth_request(request)
    key, domain = ("", "") if dev_auth else auth.clerk_configuration()

    # Only the publishable key is sent to the browser.
    return JSONResponse(
        {
            "dev_auth": dev_auth,
            "publishable_key": key,
            "domain": domain,
        },
        headers={
            "Cache-Control": "no-store",
        },
    )


@router.post('/api/logout')
def frontend_logout(request: Request):
    # Idempotent even after Clerk revokes the session. No tokens, project files or drafts
    # are read/deleted here; Clerk owns provider revocation, this clears our cookie fallback.
    origin = request.headers.get('origin')
    if origin and origin not in auth.authorized_parties():
        raise HTTPException(403, 'Origin not allowed.')
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Origin not allowed.')
    response = JSONResponse({'signed_out': True}, headers={'Cache-Control':'no-store'})
    response.delete_cookie('__session', path='/')
    return response


@router.get("/api/session")
def frontend_session(request: Request):
    job_service.metadata_store().ensure_user(request.state.user_id)
    # The middleware has established the request identity.
    payload = {"user_id": request.state.user_id}
    if getattr(request.state, "dev_auth", False):
        payload["dev"] = True
    return JSONResponse(
        payload,
        headers={
            "Cache-Control": "no-store",
        },
    )


def make_frontend_endpoint(filename):
    def endpoint():
        return serve_new_page(filename)

    return endpoint


# Serve only these named files, not the entire folder.
for frontend_filename in sorted(config.FRONTEND_FILES):
    router.add_api_route(
        "/" + frontend_filename,
        make_frontend_endpoint(
            frontend_filename
        ),
        methods=["GET"],
        include_in_schema=False,
    )


@router.get('/settings', include_in_schema=False)
def settings_page():
    return serve_new_page('settings_C.html')



