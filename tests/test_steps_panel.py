"""The website's "What the agent is doing" panel, run against the real flow_C.js with a stand-in DOM."""
import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipIf(shutil.which("node") is None, "Node.js is not installed")
class StepsPanelTests(unittest.TestCase):
    def test_steps_panel_behaviour(self):
        script = Path(__file__).resolve().parent / "steps_panel_check.js"
        result = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ALL PASSED", result.stdout)


if __name__ == "__main__":
    unittest.main()
