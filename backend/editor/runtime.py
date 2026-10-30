"""Request-time services from their owning core modules."""

def jobs_dir(*args, **kwargs):
    from backend.core.jobs import JOBS_DIR as service
    return service

def load_json(*args, **kwargs):
    from backend.core.jobs import load_json as service
    return service(*args, **kwargs)

def save_json(*args, **kwargs):
    from backend.core.jobs import save_json as service
    return service(*args, **kwargs)

def metadata_exists(*args, **kwargs):
    from backend.core.jobs import metadata_exists as service
    return service(*args, **kwargs)

def s3_client(*args, **kwargs):
    from backend.core.storage import s3_client as service
    return service(*args, **kwargs)

def public_clip(*args, **kwargs):
    from backend.core.storage import public_clip as service
    return service(*args, **kwargs)
