# SpotifyManager

Keep your Spotify parent playlists filled with the songs from their children.

```text
Indie Rock -> Rock -> All Music
Jazz ----------------> All Music
```

Add a song to a child playlist, and the next sync appends it to the configured parents if it is missing. Multiple relationships and nested parents are supported. Existing songs and playlist order are preserved; **nothing is deleted**. Your first sync also copies songs already in the children.

## What you need

- **Python 3.10 or newer.** No third-party packages are required.
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

## 2. Set up a virtual environment

Open **PowerShell** and enter the project folder:

```powershell
Set-Location -LiteralPath 'C:\Users\Matheus V Bellini\Desktop\Projects\SpotifyManager'
```

If Python is installed and available on your PATH:

```powershell
python -m venv .venv
```

Alternatively, this computer has Codex's bundled Python:

```powershell
$BasePython = 'C:\Users\Matheus V Bellini\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $BasePython -m venv .venv
```

Choose **one** of those methods. Then select the virtual environment's Python and install the requirements:

```powershell
$Python = (Resolve-Path '.\.venv\Scripts\python.exe').Path
& $Python -m pip install -r '.\requirements.txt'
```

`requirements.txt` currently contains only comments because the script uses Python's built-in libraries. The install command keeps the setup consistent if dependencies are added later.

Every time you open a new PowerShell session, return to this folder and set `$Python` again. The commands below invoke the virtual environment directly, so **activation is optional**. If you prefer activation, use `.\.venv\Scripts\Activate.ps1`; direct invocation still works if PowerShell blocks activation scripts.

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

Both JSON files already exist locally. On a fresh checkout, create any missing files without overwriting your settings:

```powershell
if (-not (Test-Path '.\config.json')) {
    Copy-Item '.\config.example.json' '.\config.json'
}
if (-not (Test-Path '.\credentials.json')) {
    Copy-Item '.\credentials.example.json' '.\credentials.json'
}
```

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

The script automatically reads `credentials.json` beside the configuration. You can choose other files with `--config` and `--credentials`:

```powershell
& $Python '.\spotify_sync.py' sync --config '.\other-playlists.json' --credentials '.\credentials.other.json' --dry-run
```

Keep alternate credentials files named `credentials*.json`, or add an explicit Git ignore rule for another filename.

## 4. Authorize, preview, and sync

After filling in both files, run these commands **one at a time**.

### Authorize once

```powershell
& $Python '.\spotify_sync.py' auth
```

A browser opens. Log in to the account that owns or collaborates on your playlists and approve permissions. Finish within five minutes. Future runs refresh tokens automatically; run `auth` again if access is revoked.

If the browser does not open, run `auth --no-browser` and open the printed URL on the **same computer**.

### Preview changes

```powershell
& $Python '.\spotify_sync.py' sync --dry-run
```

Check the missing-item counts and `Would add` messages. Preview reads Spotify and simulates additions to nested parents without changing any playlist. It can refresh tokens, update the local cache, or reconcile a previous pending write.

### Add missing songs

```powershell
& $Python '.\spotify_sync.py' sync
```

Run this again whenever you want to check for more songs. Removing a song from a child never removes it from a parent. Removing it from a parent while it remains in a child makes it eligible to be added again on a later sync.

## 5. Schedule automatic checks

After a successful manual sync, create a Windows task that checks every 15 minutes:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\register-task.ps1' -PythonPath $Python -EveryMinutes 15
```

This creates **SpotifyManager Playlist Sync** under your Windows account. It starts after one minute, then repeats while your account is logged in and the computer is awake. It uses the virtual environment's Python directly and chooses `pythonw.exe` when available to avoid a console window. Overlapping scheduled runs are ignored.

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

The helper refuses to overwrite an existing task. To change its interval or Python path, remove the old task and register it again.

### Alternative: keep a terminal running

```powershell
& $Python '.\spotify_sync.py' sync --watch 900 --log-file '.\sync.log'
```

This waits 900 seconds after each run. Press **Ctrl+C** to stop. Transient read/cooldown failures are retried on the next cycle; errors needing attention stop the watcher. Choose either the watcher or Task Scheduler for the same project.

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

If an append times out or Spotify returns a server error, the script saves the batch instead of blindly resending it. The next run checks the parent. If the batch is present, it can continue; if items are absent, it stops further writes.

Wait for Spotify to settle and inspect the parent manually. Once the uncertain request is resolved:

```powershell
& $Python '.\spotify_sync.py' acknowledge-pending
& $Python '.\spotify_sync.py' sync --dry-run
& $Python '.\spotify_sync.py' sync
```

Acknowledgement clears the local pending record after another read, even if some items are absent, allowing a later sync to add missing items. Do not acknowledge while the original request might still be running. Do not delete state to bypass this protection.

### `QUOTA_EXCEEDED`

The script saves a persistent pause and stops the watcher. Scheduled runs log the pause without sending more API requests. Reduce polling frequency and wait until Spotify quota is available, then run:

```powershell
& $Python '.\spotify_sync.py' resume
& $Python '.\spotify_sync.py' sync --dry-run
```

`resume` preserves timed cooldowns and pending writes. Spotify's quota documentation does not specify a universal reset time.

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

## Linux/macOS

After configuring the app and playlists:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python spotify_sync.py auth
.venv/bin/python spotify_sync.py sync --dry-run
.venv/bin/python spotify_sync.py sync
```

For cron, use absolute paths and the same OS account that owns the tokens. Adapt this example to your installation:

```cron
*/15 * * * * /home/YOU/SpotifyManager/.venv/bin/python /home/YOU/SpotifyManager/spotify_sync.py sync --config /home/YOU/SpotifyManager/config.json --log-file /home/YOU/SpotifyManager/sync.log
```

Authorization's browser must reach the script's loopback callback. A remote server may require an appropriate SSH tunnel.

## Run the tests

```powershell
& $Python -m unittest discover -s tests -v
```

Tests use fake Spotify responses and never access your account. They cover configuration separation, authorization, propagation, duplicate handling, pagination, snapshots, token refresh, rate limits, quota pauses, locking, batching, and uncertain-write recovery. Live validation requires your app details, playlist IDs, and authorization.
