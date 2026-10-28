"""Request-time app services; lazy imports avoid a startup dependency cycle."""

def jobs_dir(*args, **kwargs):
    from app1 import JOBS_DIR as service
    return service

def load_json(*args, **kwargs):
    from app1 import load_json as service
    return service(*args, **kwargs)

def save_json(*args, **kwargs):
    from app1 import save_json as service
    return service(*args, **kwargs)

def metadata_exists(*args, **kwargs):
    from app1 import metadata_exists as service
    return service(*args, **kwargs)

def s3_client(*args, **kwargs):
    from app1 import s3_client as service
    return service(*args, **kwargs)

def public_clip(*args, **kwargs):
    from app1 import public_clip as service
    return service(*args, **kwargs)
