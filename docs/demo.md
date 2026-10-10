# Playlist synchronization demo

This example uses fictional playlists and song labels. The demo runs the project's actual synchronization function with an in-memory API substitute. It makes no Spotify requests and does not load configuration, credentials, or tokens.

![Playlist synchronization example](demo.svg)

The [PNG version](demo.png) can be used when sharing the project on social media.

## Run it

After following the installation steps in the [README](../README.md), run:

Windows:

```powershell
.\.venv\Scripts\python.exe examples/demo.py
```

macOS and Linux:

```bash
.venv/bin/python examples/demo.py
```

## What happens

The relationships are **Indie Rock → Rock → All Music** and **Jazz → All Music**. The configuration deliberately lists the larger parent first; the script still processes descendants before ancestors.

| Playlist | Before | After |
| --- | --- | --- |
| Indie Rock | Northern Lights, City Walk | Northern Lights, City Walk |
| Rock | City Walk | City Walk, Northern Lights |
| Jazz | Blue Hour | Blue Hour |
| All Music | Blue Hour | Blue Hour, City Walk, Northern Lights |

1. **Preview:** proposes one addition to Rock and two to All Music, leaving the in-memory playlists unchanged.
2. **Sync:** adds Northern Lights to Rock, then City Walk and Northern Lights to All Music. Blue Hour is already present, so it is skipped.
3. **Repeat:** adds nothing. Every playlist already contains the items supplied by its children.

The demo checks these results and exits with an error if they change unexpectedly. Real Spotify operation also involves authentication, permissions, pagination, rate limits, and uncertain-write recovery; those paths are covered separately by the offline test suite.
