"""Composition root for the editor router and adjacent posting APIs."""
from backend import post_metadata, social_youtube
from backend.services import projects_store
from backend.routers import social
from backend.editor.routes import router
from backend.editor.storage import selected, selected_video, draft_path
from backend.editor.validation import details
from backend.editor.render import export
from backend.editor.models import ExportInput


def include_editor(app):
    app.include_router(router)
    post_metadata.register(app, projects_store, selected, details)
    social.register(app, projects_store, selected, details, draft_path)
    social_youtube.register(app, projects_store, selected_video, export, ExportInput)
