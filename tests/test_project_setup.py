import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import run as launcher
import setup_env


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "Checkout with spaces"
        self.root.mkdir()
        for name in ("config.example.json", "credentials.example.json", "requirements.txt", "spotify_sync.py"):
            shutil.copyfile(PROJECT_ROOT / name, self.root / name)

    def test_initialization_preserves_existing_private_and_public_settings(self):
        config = b'{"relationships": [{"parent": "custom", "children": ["mine"]}]}\n'
        credentials = b'{"client_id": "my-private-app-setting"}\n'
        (self.root / "config.json").write_bytes(config)
        (self.root / "credentials.json").write_bytes(credentials)
        with contextlib.redirect_stdout(io.StringIO()):
            setup_env.initialize_settings(self.root)
        self.assertEqual((self.root / "config.json").read_bytes(), config)
        self.assertEqual((self.root / "credentials.json").read_bytes(), credentials)

    def test_initialization_creates_private_template_locally(self):
        with contextlib.redirect_stdout(io.StringIO()):
            setup_env.initialize_settings(self.root)
        for name in ("config.json", "credentials.json"):
            self.assertEqual((self.root / name).read_bytes(),
                             (self.root / name.replace(".json", ".example.json")).read_bytes())
        if os.name != "nt":
            self.assertEqual((self.root / "credentials.json").stat().st_mode & 0o777, 0o600)

    def test_incomplete_environment_is_not_overwritten(self):
        environment = self.root / ".venv"
        environment.mkdir()
        sentinel = environment / "keep-this-file"
        sentinel.write_text("existing files", encoding="utf-8")
        with patch.object(setup_env, "PROJECT_ROOT", self.root), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(setup_env.main([]), 2)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "existing files")

    def test_missing_environment_does_not_use_a_global_fallback(self):
        with patch.object(launcher, "PROJECT_ROOT", self.root), patch.object(launcher.subprocess, "call") as call, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(launcher.main(["sync"]), 2)
            call.assert_not_called()

    def test_fresh_checkout_and_launch_from_another_directory(self):
        for name in ("setup_env.py", "run.py", "run-sync.ps1", "run-sync.sh"):
            shutil.copyfile(PROJECT_ROOT / name, self.root / name)
        outside = self.root.parent
        setup_command = [sys.executable, str(self.root / "setup_env.py")]
        created = subprocess.run(setup_command, cwd=outside, capture_output=True, text=True, timeout=120)
        self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
        self.assertTrue(setup_env.environment_python(self.root).is_file())
        self.assertFalse((outside / ".venv").exists())
        # A repeated setup must retain the user's edited settings.
        config = {"include_episodes": True, "relationships": [{"parent": "A" * 22, "children": ["B" * 22]}]}
        (self.root / "config.json").write_text(json.dumps(config), encoding="utf-8")
        repeated = subprocess.run(setup_command, cwd=outside, capture_output=True, text=True, timeout=120)
        self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
        self.assertEqual(json.loads((self.root / "config.json").read_text(encoding="utf-8")), config)
        help_result = subprocess.run([sys.executable, str(self.root / "run.py"), "--help"],
                                     cwd=outside, capture_output=True, text=True, timeout=30)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("--credentials", help_result.stdout)
        invalid = subprocess.run([sys.executable, str(self.root / "run.py"), "not-a-command"],
                                 cwd=outside, capture_output=True, text=True, timeout=30)
        self.assertEqual(invalid.returncode, 2)
        if os.name == "nt":
            # Expected placeholder validation, proving the default project Python ran.
            helper = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                     "-File", str(self.root / "run-sync.ps1"), "-Preview"],
                                    cwd=outside, capture_output=True, text=True, timeout=30)
            self.assertEqual(helper.returncode, 2, helper.stdout + helper.stderr)
            self.assertTrue((self.root / "sync.log").is_file())
            self.assertIn("private credentials JSON", (self.root / "sync.log").read_text(encoding="utf-8"))
        else:
            helper = subprocess.run(["bash", str(self.root / "run-sync.sh"), "--help"],
                                    cwd=outside, capture_output=True, text=True, timeout=30)
            self.assertEqual(helper.returncode, 0, helper.stdout + helper.stderr)


if __name__ == "__main__":
    unittest.main()
