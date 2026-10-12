# SpotifyManager

[![Cross-platform tests](https://github.com/MatheusVBellini/SpotifyManager/actions/workflows/tests.yml/badge.svg)](https://github.com/MatheusVBellini/SpotifyManager/actions/workflows/tests.yml)
[![License: PolyForm Noncommercial](https://img.shields.io/badge/license-PolyForm%20Noncommercial-blue)](LICENSE)

SpotifyManager keeps larger Spotify playlists updated from smaller ones. Configure which playlists feed into each parent, then run a sync to append missing songs. It runs locally from the command line and supports nested relationships.

![Example: Indie Rock flows into Rock, and Rock and Jazz flow into All Music. Three missing items are added while existing items are preserved.](docs/demo.svg)

In this example, a song added to Indie Rock reaches Rock and All Music on the next sync. Songs already present in a parent are skipped.

[Installation](#installation) · [Spotify setup](#spotify-app-setup) · [Configuration](#configuration) · [First sync](#usage) · [Scheduling](#automatic-synchronization) · [Troubleshooting](#troubleshooting)

## How synchronization works

Each relationship has a **parent** that receives songs and one or more **children** that supply them. SpotifyManager uses the Spotify Web API to read those playlists and append missing items.

- **Add-only synchronization:** keep the parent's existing items and order.
- **Multiple relationships:** combine several children into one parent, or send one child to several parents.
- **Nested relationships:** copy songs through several levels in one run.
- **Preview mode:** inspect proposed additions before changing playlists.
- **Manual or scheduled runs:** sync once, keep a terminal watcher open, or use your operating system's scheduler.
- **Recovery checks:** save progress, respect API cooldowns, and confirm uncertain additions before allowing more writes.

Relationships connect playlists, not Spotify playlist folders. Songs flow from children to parents. Deletions and changes in a parent do not flow back to its children, and existing duplicates are left in place.

The first sync includes songs already in the children. Later additions appear in the parents on the next successful run.

## Try the demo

After [installation](#installation), try the offline demo with fictional playlists. It runs the project's synchronization logic in memory, without a Spotify account or network access. Your settings and playlists are unchanged.

Windows:

```powershell
.\.venv\Scripts\python.exe examples/demo.py
```

macOS and Linux:

```bash
.venv/bin/python examples/demo.py
```

The demo previews three additions, syncs two levels of parents, then runs again to confirm that nothing needs adding. See the [walkthrough](docs/demo.md) for the playlists and results.

## Requirements

- Python **3.10 or newer**, with `venv` and `pip` support.
- Windows, macOS, or Linux.
- A Spotify developer app and an account authorized to use it.
- Ownership or collaborator access to every configured playlist, including permission to edit the parents.
- Internet access for authorization and synchronization.

The application uses Python's standard library. Setup reads `requirements.txt`, which currently lists no third-party packages.

For current Spotify Development Mode apps, the app owner needs **Spotify Premium**, and the app supports up to **five authorized users**. Accounts must be on the app's allowlist. Following a public playlist alone does not grant access to its items through the current endpoint. Check Spotify's [quota modes](https://developer.spotify.com/documentation/web-api/concepts/quota-modes) and [playlist access requirements](https://developer.spotify.com/documentation/web-api/reference/get-playlists-items) before setting up an app. These requirements were checked against Spotify's documentation on October 12, 2026.

## Installation

Clone the repository:

```console
git clone https://github.com/MatheusVBellini/SpotifyManager.git
cd SpotifyManager
```

You can also download and extract the repository ZIP. Run the commands below from the project folder containing `setup_env.py`.

### Windows

Install [Python](https://www.python.org/downloads/windows/), then open PowerShell in the project folder:

```powershell
python --version
python setup_env.py
```

If Python is available through the `py` launcher instead, use:

```powershell
py -3 --version
py -3 setup_env.py
```

### macOS

Install a supported Python version from the [macOS downloads page](https://www.python.org/downloads/macos/). With the python.org installer, also run **Install Certificates.command** from its Python folder in Applications to enable HTTPS connections. See the [official macOS installation guide](https://docs.python.org/3/using/mac.html).

In Terminal, from the project folder:

```bash
python3 --version
python3 setup_env.py
```

### Linux

Install Python 3.10 or newer with virtual environment support. On Ubuntu or Debian:

```bash
sudo apt update
sudo apt install python3 python3-venv
```

For other distributions, use the distribution's package manager to install Python and its `venv`/`pip` support. [Ubuntu's Python guide](https://ubuntu.com/developers/docs/howto/python-setup/) provides additional setup information.

```bash
python3 --version
python3 setup_env.py
```

### Local environment

Setup creates `.venv`, installs the dependencies listed in `requirements.txt`, and creates missing settings files from the examples. It preserves existing settings. The commands in this guide select the project interpreter directly, so you do not need to activate the environment.

If the project is moved or installed on another computer, recreate `.venv` in its new location using `setup_env.py`. Virtual environments depend on their original paths and base Python installation. See the [Python venv documentation](https://docs.python.org/3/library/venv.html).

## Spotify app setup

1. Open the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and create an app, or select an existing one.
2. Select **Web API** when choosing the API type.
3. Add this redirect URI in the app settings:

   ```text
   http://127.0.0.1:8888/callback
   ```

4. Copy the app's **Client ID**.
5. In **Users Management**, ensure the Spotify account used for synchronization is allowed to use the app.

Authorization uses [Authorization Code with PKCE](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow), so no client secret is required. Keep the configured redirect URI consistent with the app settings. Spotify permits HTTP for explicit loopback addresses such as `127.0.0.1`, but does not accept `localhost`. [Redirect URI requirements](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri).

The authorization requests these permissions: `playlist-read-private`, `playlist-read-collaborative`, `playlist-modify-private`, and `playlist-modify-public`. See Spotify's [scope documentation](https://developer.spotify.com/documentation/web-api/concepts/scopes).

## Configuration

Two JSON files separate Spotify app settings from playlist relationships.

### App settings: `credentials.json`

Set the Client ID copied from the developer dashboard:

```json
{
  "client_id": "PASTE_YOUR_SPOTIFY_CLIENT_ID_HERE",
  "redirect_uri": "http://127.0.0.1:8888/callback"
}
```

Setup creates this file from `credentials.example.json` if it is missing. Account access and refresh tokens are saved in `.spotify-sync/` after authorization. Keep those tokens private. Later runs refresh authorization automatically when possible.

### Playlist relationships: `config.json`

Setup creates `config.json` from `config.example.json` if it is missing. Edit the generated file and replace every playlist placeholder. If you already have a configured file, keep it when updating.

In Spotify, use **Share → Copy link to playlist** to obtain each reference. This example connects Indie Rock to Rock, then Rock and Jazz to All Music:

```json
{
  "include_episodes": false,
  "relationships": [
    {
      "_comment": "All Music receives Rock and Jazz",
      "parent": "PASTE_ALL_MUSIC_PLAYLIST_URL_OR_ID",
      "children": [
        "PASTE_ROCK_PLAYLIST_URL_OR_ID",
        "PASTE_JAZZ_PLAYLIST_URL_OR_ID"
      ]
    },
    {
      "_comment": "Rock receives Indie Rock",
      "parent": "PASTE_ROCK_PLAYLIST_URL_OR_ID",
      "children": ["PASTE_INDIE_ROCK_PLAYLIST_URL_OR_ID"]
    }
  ]
}
```

| Setting | Meaning |
| --- | --- |
| `parent` | Playlist that receives missing items. |
| `children` | Playlists that supply items to that parent. |
| `include_episodes` | Set to `true` to include podcast episodes. Defaults to `false`. |
| `_comment` | Optional descriptive text, ignored by the script. |

Playlist URLs, 22-character IDs, and `spotify:playlist:...` URIs are accepted. Use `_comment` fields for notes. Standard JSON does not support `#` or `//` comments or trailing commas.

List only the direct children of each parent. Here, Indie Rock reaches All Music through Rock. It does not need a separate relationship to All Music. The script processes nested relationships in the correct order regardless of their order in the file, and rejects cycles or self-references.

## Usage

After editing both JSON files:

1. Run `auth` and approve access in the browser.
2. Run `sync --dry-run` and review the proposed additions.
3. Run `sync` when you are ready to add those songs.

Run the commands **one at a time**.

### Windows

```powershell
.\.venv\Scripts\python.exe run.py auth
.\.venv\Scripts\python.exe run.py sync --dry-run
.\.venv\Scripts\python.exe run.py sync
```

### macOS and Linux

```bash
.venv/bin/python run.py auth
.venv/bin/python run.py sync --dry-run
.venv/bin/python run.py sync
```

| Command | Behavior |
| --- | --- |
| `auth` | Opens a browser for Spotify login and permission approval. |
| `sync --dry-run` | Reads playlists and previews additions without writing to Spotify playlists. |
| `sync` | Runs one synchronization and exits. |

During authorization, sign in to the account with access to the configured playlists and finish within five minutes. If the browser does not open, add `--no-browser` and open the printed URL in a browser on the same computer. Reauthorize if access is revoked or token refresh fails.

The preview shows missing-item counts and `Would add` messages, including propagation through nested parents. It still makes API requests and may refresh tokens or update local cache/recovery state, so it consumes API quota.

Run `sync` again to check for new songs, or configure a schedule below. Removing a song from a child does not remove it from a parent. Removing it from a parent while it remains in a child makes it eligible to be added again.

### Options and logging

Append logs with `--log-file sync.log`. Use `--config` and `--credentials` to select other settings files. For example, on macOS or Linux:

```bash
.venv/bin/python run.py sync --config other-playlists.json --credentials credentials.other.json --dry-run
.venv/bin/python run.py sync --log-file sync.log
.venv/bin/python run.py --help
```

On Windows, use `.\.venv\Scripts\python.exe` in place of `.venv/bin/python`. Explicit relative file paths are resolved from the terminal's current folder. Default settings are located beside the application; credentials default to `credentials.json` beside the selected configuration.

## Automatic synchronization

After authorizing and completing a manual sync, choose a method from the [scheduling guide](docs/scheduling.md):

| Method | When it runs |
| --- | --- |
| [Windows Task Scheduler](docs/scheduling.md#windows-task-scheduler) | At a repeating interval while your account is logged in and the computer is awake. |
| [macOS launchd](docs/scheduling.md#macos-launchd) | At a chosen time while your account is logged in. |
| [Linux cron](docs/scheduling.md#linux-cron) | At a chosen time while the machine is running. |
| [Terminal watcher](docs/scheduling.md#alternative-terminal-watcher) | At a repeating interval while the terminal stays open. |

Start with a daily schedule and adjust it to your needs and Spotify's API limits. Use one scheduling method per installation. The guide includes setup commands, status checks, and instructions for changing or removing each schedule.

## Troubleshooting

| Problem | Resolution |
| --- | --- |
| Windows says Python was not found | Install Python, reopen PowerShell, and try `py -3 setup_env.py`. After setup, use the explicit `.venv` interpreter shown above. |
| Missing or invalid virtual environment | Run setup; if the project was moved, move the old `.venv` aside and recreate it. |
| HTTPS certificate error on macOS | Run **Install Certificates.command** supplied with the python.org installer. |
| Invalid JSON | Remove comments and trailing commas. Use double-quoted strings and JSON booleans `true`/`false`. |
| Invalid Client ID or playlist reference | Replace all placeholders in both settings files. |
| Authorization fails | Check the Client ID, exact redirect URI, account allowlist, and browser callback. |
| HTTP 401 | Run `auth` again if token refresh cannot restore access. |
| HTTP 403 | Check the app owner's Premium status and account allowlist. Confirm the granted scopes and playlist ownership or collaborator access. |
| HTTP 404 | Check the playlist reference and account access. |
| Another instance holds the lock | Wait for the current run to finish, or stop the other watcher. |
| Scheduled run fails | Inspect `sync.log` and, on macOS, `scheduler.log`. Check the interpreter and project paths in the [scheduling guide](docs/scheduling.md). |

Logs append over time. Archive or truncate them periodically while no run is active.

### API rate limits and quota cooldowns

Spotify applies both short-term [rate limits](https://developer.spotify.com/documentation/web-api/concepts/rate-limits) and Development Mode [request quotas](https://developer.spotify.com/documentation/web-api/concepts/quota-modes). Development quotas are shared across apps belonging to the same developer account; creating another app does not provide an independent allowance.

For `QUOTA_EXCEEDED`, SpotifyManager saves a retry deadline. Scheduled runs and the watcher make no Spotify requests during the cooldown, and the next run after the deadline retries automatically. **No manual `resume` command is normally needed.**

The cooldown honors `Retry-After`, with a minimum of one hour. Repeated quota failures increase that minimum to 2, 4, 8, 16, and then 24 hours. Longer server-requested cooldowns take precedence. A successful sync or preview resets this backoff. The script does not assume a fixed quota reset time.

Increase the scheduling interval if limits recur. Repeated previews also consume requests. The optional `resume` command preserves the cooldown deadline and pending additions. It cannot increase the allowance or enable an early retry.

### Uncertain additions

If an addition times out, returns a server error, or cannot be confirmed in fresh playlist contents, the script saves the pending batch and stops further writes. A later sync checks it again and continues automatically when all items are present.

If items remain absent, wait for Spotify to settle and inspect the affected parent. Once the original request is known to be resolved, acknowledge the pending batch and preview again:

```powershell
.\.venv\Scripts\python.exe run.py acknowledge-pending
.\.venv\Scripts\python.exe run.py sync --dry-run
.\.venv\Scripts\python.exe run.py sync
```

On macOS or Linux, replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`.

Acknowledgement performs another read, then clears the pending record even if items are absent. A later sync may add them. Only acknowledge after resolving the uncertainty: a late original addition could otherwise create duplicates. Keep `.spotify-sync/` intact so the recovery checks retain their state.

## Behavior and limitations

- Duplicate checks use Spotify item URIs, including relinking aliases when available. Different releases or remasters can remain separate items, and existing duplicates are preserved.
- Local files and entries that are null or unsupported are skipped and reported. Catalog availability for playback can vary by country.
- Playlist snapshot checks detect changes during reads and before append batches. Changes made to children during a run are picked up on a later run.
- A partial failure does not undo confirmed additions. Subsequent runs compare against current playlist contents.
- Spotify's append endpoint does not offer an idempotency key or conditional snapshot parameter. Concurrent edits by other apps/users, or a very late uncertain request, can still cause duplicates. Use one manager for overlapping parent playlists.
- The project uses the current `/playlists/{id}/items` endpoints. Spotify API permissions and quotas can change independently of this application.

| Exit code | Meaning |
| --- | --- |
| `0` | Completed successfully. |
| `1` | Transient failure, cooldown, or lock contention. |
| `2` | Configuration, authorization, or recovery issue requiring attention. |
| `130` | Interrupted. |

## Tests

The test suite uses simulated Spotify responses and does not access an account.

Windows:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

macOS and Linux:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests cover setup and configuration, authorization, nested propagation, duplicate checks, pagination, caching, API limits, and recovery from uncertain additions. They also check locking. GitHub Actions runs the suite and offline demo on each supported operating system with Python 3.10 and 3.13.

## License

SpotifyManager is available under the [PolyForm Noncommercial License 1.0.0](LICENSE). It permits noncommercial use, modification, and distribution under its terms. Commercial use or distribution requires separate permission from the copyright holder. This is a source-available project with a commercial restriction.

[Copyright notice](NOTICE.md). Licensing requests can be directed to [Matheus V Bellini](https://github.com/MatheusVBellini).
