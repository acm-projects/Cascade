"""Compatibility import; authenticated project routes live in backend.integration."""
import sys
from backend import integration as implementation
sys.modules[__name__] = implementation
