#!/usr/bin/env bash
set -euo pipefail

# Resolve this checkout even when cron starts from a different directory.
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
python="$project_root/.venv/bin/python"

if [[ ! -x "$python" ]]; then
    printf '%s\n' 'Project virtual environment missing. Run python3 setup_env.py first.' >&2
    exit 2
fi

exec "$python" "$project_root/spotify_sync.py" sync \
    --config "$project_root/config.json" \
    --log-file "$project_root/sync.log" "$@"
