#!/usr/bin/env python3
"""Create a project-local virtual environment and initialize missing settings."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parent


def environment_python(root, platform=None):
    platform = os.name if platform is None else platform
    return root / ".venv" / ("Scripts/python.exe" if platform == "nt" else "bin/python")


def initialize_settings(root):
    for filename in ("config.json", "credentials.json"):
        target = root / filename
        if target.exists():
            if not target.is_file():
                raise OSError(f"Expected a file at {target}")
            continue
        template = root / filename.replace(".json", ".example.json")
        content = template.read_bytes()
        try:
            # Exclusive creation keeps a simultaneous setup from overwriting settings.
            with target.open("xb") as handle:
                if filename == "credentials.json" and os.name != "nt":
                    target.chmod(0o600)
                handle.write(content)
        except FileExistsError:
            continue
        print(f"Created {filename} from its template.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    if sys.version_info < (3, 10):
        print("Python 3.10 or newer is required.", file=sys.stderr)
        return 2
    root = PROJECT_ROOT
    environment = root / ".venv"
    python = environment_python(root)
    try:
        for required in ("requirements.txt", "config.example.json", "credentials.example.json", "spotify_sync.py"):
            if not (root / required).is_file():
                raise OSError(f"Required project file is missing: {required}")
        if not python.is_file():
            if environment.exists() and any(environment.iterdir()):
                raise OSError(".venv is incomplete or belongs to another operating system. "
                              "Move it aside and run setup again to recreate it.")
            import venv
            print("Creating .venv inside the project...", flush=True)
            venv.EnvBuilder(with_pip=True).create(environment)
        # Detect stale environments and accidental use of an incompatible interpreter.
        subprocess.run([str(python), "-c",
                        "import sys; sys.exit(0 if sys.version_info >= (3, 10) and sys.prefix != sys.base_prefix else 1)"],
                       check=True, cwd=root)
        subprocess.run([str(python), "-m", "pip", "--disable-pip-version-check", "install",
                        "-r", str(root / "requirements.txt")], check=True, cwd=root)
        initialize_settings(root)
    except (OSError, subprocess.CalledProcessError, ImportError) as exc:
        print(f"Setup failed: {exc}", file=sys.stderr)
        print("Check that Python has venv/pip support. On Ubuntu or Debian, install python3-venv. "
              "If this project was moved, recreate .venv in its new location.", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    launcher = "python" if os.name == "nt" else "python3"
    print("Setup complete. Edit credentials.json and config.json, then run:")
    print(f"  {launcher} run.py auth")
    print(f"  {launcher} run.py sync --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
