"""Unified entrypoint for the integration branch.
Run from the repository root: uvicorn app1:app --host 127.0.0.1 --port 8000
Alternatively: uvicorn backend.app:app --host 127.0.0.1 --port 8000
Feature code from origin/main is called through integration.py so its
standalone unauthenticated routers cannot bypass Clerk or job ownership.
"""
from app1 import app
