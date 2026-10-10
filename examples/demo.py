#!/usr/bin/env python3
"""Demonstrate the real synchronization logic with fictional, in-memory playlists."""
from __future__ import annotations

import copy
import logging
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import spotify_sync as sync_app

ALL_MUSIC, ROCK, INDIE_ROCK, JAZZ = (letter * 22 for letter in "ABCD")
PLAYLIST_NAMES = {ALL_MUSIC: "All Music", ROCK: "Rock", INDIE_ROCK: "Indie Rock", JAZZ: "Jazz"}
SONG_NAMES = {
    "spotify:track:" + "n" * 22: "Northern Lights",
    "spotify:track:" + "c" * 22: "City Walk",
    "spotify:track:" + "b" * 22: "Blue Hour",
}


def item(letter):
    uri = "spotify:track:" + letter * 22
    return {"uri": uri, "aliases": [uri]}


class DemoStore:
    def __init__(self):
        self.data = {"playlists": {}}

    def save(self):
        # State remains in memory; personal configuration and tokens are untouched.
        pass


class DemoSpotify:
    def __init__(self):
        self.oauth = SimpleNamespace(token=lambda: "fictional-demo-token")
        self.contents = {
            ALL_MUSIC: [item("b")],
            ROCK: [item("c")],
            INDIE_ROCK: [item("n"), item("c")],
            JAZZ: [item("b")],
        }
        self.additions = []

    def read_playlist(self, playlist_id, force_refresh=False):
        return {
            "items": copy.deepcopy(self.contents[playlist_id]),
            "skipped": 0,
            "metadata": {"owner": {"id": "demo-user"}, "collaborative": False},
        }

    def request(self, method, path, body=None):
        if method == "GET" and path == "/me":
            return {"id": "demo-user"}
        if method != "POST" or not path.endswith("/items") or body is None:
            raise RuntimeError("Unsupported request in offline demo.")
        playlist_id = path.split("/")[2]
        for uri in body["uris"]:
            self.contents[playlist_id].append({"uri": uri, "aliases": [uri]})
            self.additions.append((playlist_id, uri))
            print(f"  Added {SONG_NAMES[uri]} -> {PLAYLIST_NAMES[playlist_id]}")
        return {"snapshot_id": "demo-snapshot"}


def display_playlists(api):
    for playlist_id in (INDIE_ROCK, ROCK, JAZZ, ALL_MUSIC):
        songs = ", ".join(SONG_NAMES[row["uri"]] for row in api.contents[playlist_id])
        print(f"  {PLAYLIST_NAMES[playlist_id]}: {songs}")


def main():
    # Deliberately put the ancestor first to demonstrate automatic ordering.
    config = {"relationships": [
        {"parent": ALL_MUSIC, "children": [ROCK, JAZZ]},
        {"parent": ROCK, "children": [INDIE_ROCK]},
    ]}
    parents, order, playlist_ids = sync_app.relationships(config)
    api, store = DemoSpotify(), DemoStore()
    before = copy.deepcopy(api.contents)

    print("SpotifyManager - offline demo (fictional playlists, no Spotify access)")
    print("\nBefore:")
    display_playlists(api)

    print("\n1. Preview: three proposed additions; playlists remain unchanged.")
    sync_app.sync(api, store, parents, order, playlist_ids, dry_run=True)
    if api.contents != before or api.additions:
        raise RuntimeError("Preview changed the demo playlists.")
    print("  Rock: Northern Lights")
    print("  All Music: City Walk, Northern Lights")

    print("\n2. Sync: propagate children into their parents.")
    sync_app.sync(api, store, parents, order, playlist_ids)
    expected = [(ROCK, item("n")["uri"]), (ALL_MUSIC, item("c")["uri"]), (ALL_MUSIC, item("n")["uri"])]
    if api.additions != expected:
        raise RuntimeError("Unexpected propagation result.")
    print("\nAfter:")
    display_playlists(api)

    print("\n3. Repeat: check again without duplicating songs.")
    sync_app.sync(api, store, parents, order, playlist_ids)
    if api.additions != expected:
        raise RuntimeError("The second sync added duplicate items.")
    print("  No new additions. Blue Hour and City Walk were each kept once.")
    print("\nDemo complete. No files or Spotify playlists were changed.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    raise SystemExit(main())
