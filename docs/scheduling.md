# Automatic synchronization

[Back to the README](../README.md#automatic-synchronization)

Authorize and complete a manual sync before scheduling. Run setup and authorization under the operating system account that will run scheduled syncs. A daily schedule is a conservative starting point; more frequent checks consume more API quota. Choose one scheduling method for each installation.

## Windows: Task Scheduler

From PowerShell in the project folder, register a daily task:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\register-task.ps1 -EveryMinutes 1440
```

This creates **SpotifyManager Playlist Sync**, with its first run about one minute after registration and a repeat interval of 24 hours. Use another value from **5 to 1440** for a different interval in minutes. It uses the project interpreter directly and runs while the account is logged in and the computer is awake. Missed starts can run when the computer becomes available again. Overlapping scheduled runs are ignored.

Check the task and recent logs:

```powershell
Get-ScheduledTaskInfo -TaskName 'SpotifyManager Playlist Sync'
Get-Content -LiteralPath '.\sync.log' -Tail 30
```

Manage the task with:

```powershell
Disable-ScheduledTask -TaskName 'SpotifyManager Playlist Sync'
Enable-ScheduledTask -TaskName 'SpotifyManager Playlist Sync'
Unregister-ScheduledTask -TaskName 'SpotifyManager Playlist Sync'
```

To change the interval or project location, remove the old task and register it again. The helper refuses to overwrite an existing task. For a manual run with logging, use `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run-sync.ps1`. Add `-Preview` to preview additions.

## macOS: launchd

From Terminal in the project folder, create a user LaunchAgent for **18:00 every day**. The following generates paths from the current folder, including folder names containing spaces:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import plistlib

root = Path.cwd().resolve()
agent = Path.home() / "Library/LaunchAgents/local.spotifymanager.sync.plist"
agent.parent.mkdir(parents=True, exist_ok=True)
settings = {
    "Label": "local.spotifymanager.sync",
    "ProgramArguments": ["/bin/bash", str(root / "run-sync.sh")],
    "WorkingDirectory": str(root),
    "StartCalendarInterval": {"Hour": 18, "Minute": 0},
    "StandardOutPath": str(root / "scheduler.log"),
    "StandardErrorPath": str(root / "scheduler.log"),
}
with agent.open("wb") as handle:
    plistlib.dump(settings, handle)
agent.chmod(0o600)
print(agent)
PY

launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/local.spotifymanager.sync.plist"
```

Change `Hour` and `Minute` before creating the file to select another time. This user agent runs while the account is logged in. A calendar run missed during sleep is handled after waking. A run missed while powered off waits until the next scheduled time. See Apple's [scheduled jobs guide](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/ScheduledJobs.html) and [LaunchAgent documentation](https://support.apple.com/guide/terminal/apdc6c1077b-5d5d-4d35-9c19-60f2397b2369/mac).

Check its status and logs:

```bash
launchctl print "gui/$(id -u)/local.spotifymanager.sync"
tail -n 30 sync.log
```

Unload it before changing its schedule or moving the project:

```bash
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/local.spotifymanager.sync.plist"
```

Then regenerate and load it again. To remove scheduling permanently, unload it and delete `local.spotifymanager.sync.plist` from `~/Library/LaunchAgents`.

## Linux: cron

From the project folder, generate an entry for **18:00 every day**:

```bash
printf '0 18 * * * /bin/bash "%s/run-sync.sh"\n' "$(pwd -P)"
crontab -e
```

Paste the printed line into the crontab and save it. It uses an absolute project path and writes to `sync.log`. The machine must be running at the scheduled time. Cron does not catch up on missed runs. The schedule uses the machine's local time. Ensure the cron service is installed and enabled for the distribution.

To change or remove the schedule, edit the entry with `crontab -e`. If the project moves, regenerate the entry after recreating `.venv`.

## Alternative: terminal watcher

Keep a terminal open to repeat synchronization, waiting 24 hours after each run:

```powershell
.\.venv\Scripts\python.exe run.py sync --watch 86400 --log-file sync.log
```

On macOS or Linux:

```bash
.venv/bin/python run.py sync --watch 86400 --log-file sync.log
```

`--watch` accepts an interval in seconds, with a minimum of 300. Press **Ctrl+C** to stop. Transient failures are retried on a later cycle. Errors requiring attention stop the watcher. The terminal must remain open and the computer must stay running.
