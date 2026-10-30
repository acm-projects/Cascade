"""Explicit opt-in for manual Chrome/DevTools suites; safe during CI discovery."""
import os
import unittest


def require_browser_tests():
    if os.environ.get('CASCADE_BROWSER_TESTS') != '1':
        raise unittest.SkipTest('Set CASCADE_BROWSER_TESTS=1 and start isolated Chrome on port 9333.')
