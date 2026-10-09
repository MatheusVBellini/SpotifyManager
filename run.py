#!/usr/bin/env python3
"""Run SpotifyManager with this checkout's virtual environment."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from setup_env import environment_python

PROJECT_ROOT = Path(__file__).resolve().parent


def main(argv=None):
    python = environment_python(PROJECT_ROOT)
    if not python.is_file():
        print("Project virtual environment missing. Run python setup_env.py "
              "(python3 setup_env.py on Linux) first.", file=sys.stderr)
        return 2
    try:
        # Preserve the caller's working directory for explicit relative CLI options.
        # The app finds its default configuration beside spotify_sync.py.
        return subprocess.call([str(python), str(PROJECT_ROOT / "spotify_sync.py"),
                                *(sys.argv[1:] if argv is None else argv)])
    except OSError as exc:
        print(f"Cannot start the project environment: {exc}. Recreate .venv with setup_env.py.", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
