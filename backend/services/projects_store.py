"""Owner-scoped updates to project source preparation state."""
from backend import integration as store
from backend.services.sessions import save


def update_source(project_id, user_id, job_id, **changes):
    # Reload under the lock: preparation must not overwrite newer sessions/selections.
    with store.lock:
        project = store.require_project(project_id, user_id)
        if project.get('source_job') != job_id:
            return False
        project.update(changes)
        save(project)
        return True
