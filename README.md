# SpotifyManager

Keep your Spotify parent playlists filled with the songs from their children.

```text
Indie Rock -> Rock -> All Music
Jazz ----------------> All Music
```

Add a song to a child playlist, and the next sync appends it to the configured parents if it is missing. Multiple relationships and nested parents are supported. Existing songs and playlist order are preserved; **nothing is deleted**. Your first sync also copies songs already in the children.

## What you need

- **Python 3.10 or newer**, installed on your computer. No third-party packages are required.
- A Spotify developer app whose owner has active **Premium**.
- A Spotify account on the app's allowlist.
- Playlists you **own or collaborate on**, with editing access to the parents.

Following somebody's public playlist does not grant API access to its contents. Spotify requirements were checked on **October 9, 2026**. [Quota modes](https://developer.spotify.com/documentation/web-api/concepts/quota-modes), [playlist access](https://developer.spotify.com/documentation/web-api/reference/get-playlists-items).

## 1. Create your Spotify app

1. Open the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard), sign in, and create an app or select an existing one.
2. Select **Web API** if asked for the API type.
3. Register this exact redirect URI in the app settings:

   ```text
   http://127.0.0.1:8888/callback
   ```

4. Copy the app's **Client ID**.
5. Under **Users Management**, ensure the Spotify account you will log in with is allowed to use the app.

The script uses [Authorization Code with PKCE](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow). No client secret is needed. Use `127.0.0.1`; Spotify does not accept `localhost` for this redirect. [Redirect URI requirements](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri).

## 2. Download and set up the project

Clone the repository, or download its ZIP from GitHub and extract it. This repository is private, so you need access to clone or download it.

```console
git clone https://github.com/MatheusVBellini/SpotifyManager.git
cd SpotifyManager
```

If you downloaded a ZIP, open a terminal inside the extracted folder containing `spotify_sync.py`. Run the commands below from that project folder; no particular drive, username, or installation location is required.

### Windows (PowerShell)

Install [Python 3.10 or newer](https://www.python.org/downloads/) and make it available as `python`. Then run:

```powershell
python --version
python setup_env.py
```

If your Windows installation uses the `py` launcher instead, use `py -3 setup_env.py` and `py -3 run.py ...` in place of the `python` commands.

### Linux

Use Python 3.10 or newer with virtual environment support. On Ubuntu or Debian, install the system prerequisites if needed:

```bash
sudo apt update
sudo apt install python3 python3-venv
```

For other distributions, install Python and its venv support with your distribution's package manager. [Ubuntu Python setup](https://documentation.ubuntu.com/ubuntu-for-developers/howto/python-setup/).

```bash
python3 --version
python3 setup_env.py
```

### What setup does

`setup_env.py` finds the project using its own location. It creates `.venv/` **inside the project**, installs `requirements.txt` using that environment's Python, and creates any missing configuration files from their templates. Existing configuration and credentials are preserved.

`run.py` automatically selects `.venv/Scripts/python.exe` on Windows or `.venv/bin/python` on Linux. You do not need to activate the environment or define shell variables. `requirements.txt` currently contains only comments because the app uses Python's built-in libraries.

All application code, launchers, templates, and the dependency manifest live in this repository. A normal installed Python interpreter is the system prerequisite. Recreate `.venv` on each computer or after relocating the checkout; virtual environments are machine-specific and should not be copied or committed. [Python virtual environment documentation](https://docs.python.org/3/library/venv.html).

```text
SpotifyManager/
  setup_env.py             Creates the local environment and missing settings
  run.py                   Runs commands using that environment
  spotify_sync.py          Spotify synchronization implementation
  requirements.txt        Dependency manifest
  config.json             Committable playlist relationships
  credentials.example.json
  credentials.json        Private app settings, created locally and ignored
  .venv/                  Local Python environment, ignored
  .spotify-sync/          Private tokens and state, created at login and ignored
  run-sync.ps1             Windows sync/logging helper
  run-sync.sh              Linux sync/logging helper
  register-task.ps1        Windows scheduling helper
```

## 3. Configure your app and playlists

The two JSON files keep app settings separate from playlist relationships:

| File | Contents | Commit to GitHub? |
| --- | --- | --- |
| `config.json` | Parent/child relationships and episode setting | Yes |
| `credentials.json` | Your Client ID and redirect URI | No; ignored |
| `config.example.json` | Playlist template | Yes |
| `credentials.example.json` | App settings template with placeholders | Yes |
| `.spotify-sync/` | Access/refresh tokens and sync state | No; ignored |
| `.venv/` | Local Python environment | No; ignored |

Setup creates any missing JSON files without overwriting your settings. Edit both files before authorizing or syncing.

### Edit `credentials.json`

Replace the Client ID placeholder with the value from your Spotify app:

```json
{
  "client_id": "PASTE_YOUR_SPOTIFY_CLIENT_ID_HERE",
  "redirect_uri": "http://127.0.0.1:8888/callback"
}
```

The Client ID identifies the app. Your private account access/refresh tokens are saved separately in `.spotify-sync/` after authorization.

### Edit `config.json`

In Spotify, use **Share -> Copy link to playlist**. Replace every placeholder, and remove any example relationship you do not need:

The committed `config.json` can contain configured playlist IDs. For another account, replace those references with your own playlists, or start from `config.example.json`.

```json
{
  "include_episodes": false,
  "relationships": [
    {
      "parent": "PASTE_ALL_MUSIC_PLAYLIST_URL_OR_ID",
      "children": [
        "PASTE_ROCK_PLAYLIST_URL_OR_ID",
        "PASTE_JAZZ_PLAYLIST_URL_OR_ID"
      ]
    },
    {
      "parent": "PASTE_ROCK_PLAYLIST_URL_OR_ID",
      "children": ["PASTE_INDIE_ROCK_PLAYLIST_URL_OR_ID"]
    }
  ]
}
```

- **`parent`** receives missing songs.
- **`children`** supply songs. One child can feed several parents.
- **`include_episodes`** defaults to `false`; set it to `true` to include podcast episodes.

Playlist URLs, 22-character playlist IDs, and `spotify:playlist:...` URIs are accepted. Nested relationships propagate in one run regardless of configuration order. Cycles and self-references are rejected.

List the direct children of each parent. For example, if Indie Rock feeds Rock and Rock feeds All Music, All Music only needs Rock in its children; Indie Rock reaches it through Rock. A child can still feed several independent parents, and shared songs are added once per parent.

The script automatically reads `credentials.json` beside the configuration. You can choose other files with `--config` and `--credentials`:

```powershell
python run.py sync --config other-playlists.json --credentials credentials.other.json --dry-run
```

On Linux use `python3` instead of `python`. Explicit relative paths are resolved from your terminal's current folder. Default settings are located beside the app, so `run.py` also works when invoked from a different folder. Keep alternate credentials files named `credentials*.json`, or add an explicit Git ignore rule for another filename.

## 4. Authorize, preview, and sync

After filling in both files, run these commands **one at a time**.

### Windows

```powershell
python run.py auth
python run.py sync --dry-run
python run.py sync
```

### Linux

```bash
python3 run.py auth
python3 run.py sync --dry-run
python3 run.py sync
```

**Authorize:** a browser opens. Log in to the account that owns or collaborates on your playlists and approve permissions. Finish within five minutes. Future runs refresh tokens automatically; authorize again if access is revoked. If the browser does not open, add `--no-browser` to the auth command and open its printed URL on the same computer.

**Preview:** check the missing-item counts and `Would add` messages. Preview reads Spotify and simulates additions to nested parents without changing any playlist. It can refresh tokens, update the local cache, or reconcile a previous pending write.

**Sync:** append the missing items.

Run this again whenever you want to check for more songs. Removing a song from a child never removes it from a parent. Removing it from a parent while it remains in a child makes it eligible to be added again on a later sync.

## 5. Schedule automatic checks

### Windows Task Scheduler

After a successful manual sync, create a task that checks every 15 minutes:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\register-task.ps1 -EveryMinutes 15
```

The helper finds the virtual environment and app files relative to its own location. It creates **SpotifyManager Playlist Sync** under your Windows account, starting after one minute and repeating while your account is logged in and the computer is awake. It uses `pythonw.exe` when available to avoid a console window. Overlapping scheduled runs are ignored. An optional `-PythonPath` can override the project interpreter.

Change `15` to your preferred interval in minutes; the helper accepts 5 to 1440. Longer intervals reduce quota usage. This is polling: changes appear after the next successful check.

### Check activity

```powershell
Get-Content -LiteralPath '.\sync.log' -Tail 30
Get-ScheduledTaskInfo -TaskName 'SpotifyManager Playlist Sync'
```

Logs append indefinitely. Archive or truncate `sync.log` periodically when no run is active.

### Disable, enable, or remove the task

```powershell
Disable-ScheduledTask -TaskName 'SpotifyManager Playlist Sync'
Enable-ScheduledTask -TaskName 'SpotifyManager Playlist Sync'
Unregister-ScheduledTask -TaskName 'SpotifyManager Playlist Sync'
```

The helper refuses to overwrite an existing task. To change its interval or after moving the project, remove the old task and register it again. For a manual sync with logging, run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run-sync.ps1`; append `-Preview` for a preview.

### Linux cron

After a successful manual sync, the Linux helper provides the same project-relative configuration and logging:

```bash
bash run-sync.sh --dry-run
bash run-sync.sh
tail -n 30 sync.log
```

To schedule it, generate a cron line using your checkout's current location:

```bash
printf '*/15 * * * * /bin/bash "%s/run-sync.sh"\n' "$(pwd -P)"
crontab -e
```

Paste the printed line into your crontab. It checks every 15 minutes and writes to the project's `sync.log`, even when cron starts from another directory. The machine must be awake. Use the same OS account that authorized Spotify. If you move the checkout, recreate `.venv` and regenerate the cron line. Remove the line with `crontab -e` to stop scheduling.

### Alternative: keep a terminal running

```powershell
python run.py sync --watch 900 --log-file sync.log
```

On Linux use `python3 run.py sync --watch 900 --log-file sync.log`. This waits 900 seconds after each run. Press **Ctrl+C** to stop. Transient read/cooldown failures are retried on the next cycle; errors needing attention stop the watcher. Choose either the watcher or an OS schedule for the same project.

## GitHub and private files

Commit the code, `config.json`, `requirements.txt`, and placeholder templates. Committing the configuration shares its playlist links and relationships with anyone who can read the repository.

`.gitignore` excludes `credentials*.json`, `.spotify-sync/`, `.venv/`, and logs. It allows `credentials.example.json` because that template contains placeholders. Keep real values out of example files and do not force-add ignored files.

Verify before committing:

```powershell
git check-ignore credentials.json .spotify-sync/token.json .venv/pyvenv.cfg
git status --short
```

The first command should list the private/local paths. Credentials and tokens should not appear in the status listing. Ignore rules do not remove files already tracked in another checkout.

On Windows, credential/token files inherit the project's access controls and are not encrypted; keep them in your user folder. Generated token/state files have restrictive permissions on POSIX systems.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Invalid Client ID or playlist reference | Replace every placeholder in both JSON files. |
| Credentials file missing | Copy the credentials template and fill it in. |
| Credentials in the public config | Move app settings to `credentials.json`. |
| Authorization fails | Check the Client ID and exact redirect URI in Spotify app settings. |
| HTTP 401 | Run `auth` again if automatic token refresh cannot restore access. |
| HTTP 403 | Check Premium, allowlist, permissions, and owner/collaborator access. |
| HTTP 404 | Check the playlist ID and account access. |
| Rate limited / cooldown active | Wait for the cooldown; increase the interval if this happens often. |
| Another instance holds the lock | Stop the watcher or wait for the other run to finish. |
| Task already exists | Remove it before registering a replacement. |
| Task result `0x2` | Inspect `sync.log` for the error needing attention. |

### Uncertain previous addition

If an append times out or Spotify returns a server error, the script saves the batch instead of blindly resending it. The next run checks the parent using fresh contents rather than the cache. If the batch is present, it can continue; if items are absent, it stops further writes.

After a successful append response, the script checks fresh contents and, if needed, rechecks after 2, 5, and 10 seconds. These checks never resend the addition. If the songs are still absent, it retains the pending record and stops before writing to further parents. Wait briefly and rerun so it can confirm the addition and continue propagation.

Wait for Spotify to settle and inspect the parent manually. Once the uncertain request is resolved:

```powershell
python run.py acknowledge-pending
python run.py sync --dry-run
python run.py sync
```

On Linux replace `python` with `python3`. Acknowledgement clears the local pending record after another read, even if some items are absent, allowing a later sync to add missing items. Do not acknowledge while the original request might still be running. Do not delete state to bypass this protection.

### `QUOTA_EXCEEDED`

The script saves the quota pause and a retry time. Scheduled runs and the watcher send no Spotify requests during that cooldown. The next run after the deadline retries automatically; **you normally do not need `resume` or to register your scheduled task again**. Existing saved pauses with a retry time also recover automatically.

The cooldown respects Spotify's `Retry-After` and has a minimum of one hour. Consecutive quota failures increase that minimum to 2, 4, 8, 16, and then 24 hours. A longer Spotify cooldown still takes precedence. A successful sync or preview resets this backoff. Older pauses without a valid retry time get a one-hour cooldown on their first run.

If Spotify still reports quota exceeded, the script saves a new cooldown and waits for a later run. It does not assume that the quota resets at a particular time. Keep polling infrequent and avoid repeated previews, which also consume API requests.

The optional manual command remains available:

```powershell
python run.py resume
```

On Linux replace `python` with `python3`. `resume` preserves the cooldown deadline and pending writes; it does not increase Spotify's allowance or allow an early request. Uncertain additions still require confirmation before further writes.

## Behavior and limits

- Duplicate checks use Spotify URIs; different releases/remasters can remain separate items. Existing duplicates are preserved. Relinking aliases are considered when supplied by Spotify.
- Local files, null items, and unsupported entries are skipped and counted in logs. A valid catalog URI can still refer to a song unavailable for playback in your country.
- All playlists are read before the first addition. Snapshot checks detect changes during pagination and before append batches. Changes to children during a run are picked up later.
- Reads use bounded retries, stable contents are cached, and ordinary 429 responses honor `Retry-After`.
- A failed later batch does not undo earlier additions. A rerun continues using current playlist contents.
- Spotify's append API has no idempotency key or conditional snapshot parameter. Duplicate prevention cannot be guaranteed if another user/app adds the same song between the read and append, or an uncertain request commits very late. Use one manager per overlapping set of parents and retain its state.

Exit codes: **0** success; **1** transient failure, cooldown, or lock contention; **2** attention needed; **130** interrupted.

## Spotify API notes for 2026

The script uses the current `/playlists/{id}/items` endpoints, the `item` response field, read pages of 50, and append batches of up to 100. It tolerates the legacy response field while using current endpoints. [Get Playlist Items](https://developer.spotify.com/documentation/web-api/reference/get-playlists-items), [Add Items](https://developer.spotify.com/documentation/web-api/reference/add-items-to-playlist).

New Development Mode apps allow five authorized users; existing higher counts are grandfathered. The [July 2026 changelog](https://developer.spotify.com/documentation/web-api/references/changes/july-2026) raised the app limit to **25** and introduced quota counting across a developer's apps. Ordinary rate limits still apply. [Migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide), [rate limits](https://developer.spotify.com/documentation/web-api/concepts/rate-limits).

The [February announcement's March 9 update](https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security) postponed endpoint changes for older integrations. New apps remained under the February restrictions; Extended Quota Mode apps are unaffected by those endpoint changes. This project targets current documented endpoints for a personal app.

Authorization requests `playlist-read-private`, `playlist-read-collaborative`, `playlist-modify-private`, and `playlist-modify-public`. [Scope documentation](https://developer.spotify.com/documentation/web-api/concepts/scopes).

## Remote Linux servers

Authorization's browser must reach the script's loopback callback on the server. For a headless server, use an appropriate SSH tunnel, run `python3 run.py auth --no-browser` on the server, and open the printed URL in your local browser through that tunnel. Later scheduled runs need no browser. Keep credentials and tokens on the server private.

## Run the tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

On Linux:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests use fake Spotify responses and never access your account. They cover setup, project-relative launching, configuration separation, authorization, propagation, duplicate handling, pagination, snapshots, token refresh, rate limits, quota pauses, locking, batching, and uncertain-write recovery. GitHub Actions checks Windows and Linux on Python 3.10 and 3.13. Live validation requires your app details, playlist IDs, and authorization.
