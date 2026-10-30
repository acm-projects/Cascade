from pathlib import Path
import os

from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_DIR / "web"

load_dotenv(PROJECT_DIR / ".env", override=True)
# Accept existing local names without rewriting the user's secrets file.
if not os.getenv('CLERK_SECRET_KEY') and os.getenv('CLERK_KEY', '').startswith('sk_'):
    os.environ['CLERK_SECRET_KEY'] = os.environ['CLERK_KEY']
if not os.getenv('CLERK_PUBLISHABLE_KEY') and os.getenv('CLERK_KEY', '').startswith('pk_'):
    os.environ['CLERK_PUBLISHABLE_KEY'] = os.environ['CLERK_KEY']
if not os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_ACCESS_KEY'):
    os.environ['AWS_ACCESS_KEY_ID'] = os.environ['AWS_ACCESS_KEY']

JOBS_DIR = PROJECT_DIR / "video_jobs"
JOBS_DIR.mkdir(exist_ok=True)

PROFILE_CACHE_SECONDS = 300
FAILURE_CACHE_SECONDS = 30

DEFAULT_FOLDER = "users"


FRONTEND_FILES = {
    "index.html",
    "canvas_branches.js",
    "index_C.html",
    "login_C.html",
    "projects_C.html",
    "canvas_C.html",
    "editor_C.html",
    "exports_C.html",
    "settings_C.html",
    "styles_C.css",
    "flow_C.js",
    "editor_C.js",
    "editor_broll.js",
    "editor_reframe.js",
    "editor_captions.js",
    "editor_timeline.js",
    "editor_state.js",
    "export_selection.js",
    "clip_navigation.js",
    "clip_navigation.css",
    "exports_C.js",
    "export_post.js",
    "post_schedule.js",
    "exports_C.css",
    "editor_C.css",
}

PRIVATE_CLIP_FIELDS = {
    "s3_bucket",
    "clip_s3_key",
    "captions_s3_key",
}

CLERK_HINTS = {
    401: "The secret key was rejected.",
    403: "Clerk refused the request.",
    404: (
        "User not found. The key may belong "
        "to a different Clerk application."
    ),
    429: "Clerk is rate limiting requests.",
}
