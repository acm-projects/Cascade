"""Editor HTTP boundary; URLs intentionally unchanged."""
from fastapi import APIRouter
from .broll_routes import stock_search, stock_media, stock_thumbnail
from .drafts import editor_index, get_draft, save_draft, save_clip
from .reframe import start_reframe, reframe_status, subjects_at, reframe_plan
from .render import export_selected, export
from .media_routes import get_thumbnail, get_media
from .chat import chat

router = APIRouter(prefix="/api/projects/{pid}/editor")
router.add_api_route('/{jid}/{index}/broll/search', stock_search, methods=['GET'])
router.add_api_route('/{jid}/{index}/broll/{asset_id}/media', stock_media, methods=['GET'])
router.add_api_route('/{jid}/{index}/broll/{asset_id}/thumbnail', stock_thumbnail, methods=['GET'])
router.add_api_route('', editor_index, methods=['GET'])
router.add_api_route('/{jid}/{index}/reframe', start_reframe, methods=['POST'])
router.add_api_route('/{jid}/{index}/reframe/{analysis_id}', reframe_status, methods=['GET'])
router.add_api_route('/{jid}/{index}/reframe/{analysis_id}/subjects', subjects_at, methods=['GET'])
router.add_api_route('/{jid}/{index}/reframe/{analysis_id}/plan', reframe_plan, methods=['POST'])
router.add_api_route('/{jid}/{index}', get_draft, methods=['GET'])
router.add_api_route('/{jid}/{index}', save_draft, methods=['PUT'])
router.add_api_route('/{jid}/{index}/save-clip', save_clip, methods=['POST'])
router.add_api_route('/{jid}/{index}/thumbnail', get_thumbnail, methods=['GET'])
router.add_api_route('/{jid}/{index}/media', get_media, methods=['GET'])
router.add_api_route('/{jid}/{index}/chat', chat, methods=['POST'])
router.add_api_route('/export-selected', export_selected, methods=['POST'])
router.add_api_route('/{jid}/{index}/export', export, methods=['POST'])
