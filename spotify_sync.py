#!/usr/bin/env python3
"""Add-only Spotify playlist sync. Python 3.10+, standard library only."""
from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import http.client
import json
import logging
import math
import os
from pathlib import Path
import random
import re
import secrets
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
import webbrowser

LOG = logging.getLogger("spotify_sync")
SCOPES = frozenset({"playlist-read-private", "playlist-read-collaborative",
                    "playlist-modify-private", "playlist-modify-public"})
API = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"
URI_PATTERN = re.compile(r"spotify:(track|episode):[A-Za-z0-9]{22}\Z")


class SyncError(Exception):
    def __init__(self, message, code=2):
        super().__init__(message)
        self.code = code


class UncertainWrite(SyncError):
    """Spotify may have committed a POST; never resend it automatically."""


def read_json(path, default=None):
    try:
        with path.open(encoding="utf-8-sig") as handle:
            result = json.load(handle)
    except FileNotFoundError:
        if default is not None:
            return default
        raise SyncError(f"File missing: {path}")
    except (ValueError, OSError) as exc:
        raise SyncError(f"Cannot read JSON file {path}: {exc}") from exc
    if not isinstance(result, dict):
        raise SyncError(f"Expected a JSON object in {path}")
    return result


def save_json(path, data):
    """Atomic replace, fsync, and private permissions on POSIX."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextlib.contextmanager
def exclusive_lock(path):
    """OS releases the lock after a crash; do not delete the lock file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    acquired = False
    try:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as exc:
            raise SyncError("Another instance holds this project's lock.", 1) from exc
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def playlist_id(value):
    if not isinstance(value, str):
        raise SyncError("Playlist references must be strings.")
    value = value.strip()
    if value.startswith("spotify:playlist:"):
        value = value.split(":")[-1]
    elif value.startswith("https://open.spotify.com/"):
        parts = urlsplit(value).path.strip("/").split("/")
        if len(parts) >= 2 and parts[-2] == "playlist":
            value = parts[-1]
    if not re.fullmatch(r"[A-Za-z0-9]{22}", value):
        raise SyncError("Use a 22-character playlist ID, Spotify playlist URI, or playlist URL.")
    return value


def load_settings(config_path, credentials_path=None):
    config = read_json(config_path)
    private_keys = {"client_id", "client_secret", "api_key", "access_token", "refresh_token"}
    if private_keys.intersection(config):
        raise SyncError("Keep app credentials out of the committable config file. Move them to credentials.json.")
    credentials_path = credentials_path or config_path.parent / "credentials.json"
    if not credentials_path.is_file():
        raise SyncError(f"Credentials file missing: {credentials_path}. Copy credentials.example.json to credentials.json and set client_id.")
    credentials = read_json(credentials_path)
    client_id = credentials.get("client_id")
    if not isinstance(client_id, str) or not re.fullmatch(r"[A-Fa-f0-9]{32}", client_id):
        raise SyncError("Set client_id in the private credentials JSON to your Spotify app's 32-character Client ID.")
    if "redirect_uri" in config:
        raise SyncError("Move redirect_uri to credentials.json so app settings stay separate from playlist relationships.")
    return config, credentials


def relationships(config):
    rows = config.get("relationships")
    if not isinstance(rows, list) or not rows:
        raise SyncError("Configure at least one relationship.")
    parents = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("children"), list) or not row["children"]:
            raise SyncError("Every relationship needs a parent and a nonempty children array.")
        parent = playlist_id(row.get("parent"))
        children = parents.setdefault(parent, [])
        for ref in row["children"]:
            child = playlist_id(ref)
            if child not in children:
                children.append(child)
    # Process descendants before their parents, independent of config order.
    done, visiting, order = set(), set(), []

    def visit(node):
        if node in visiting:
            raise SyncError("Playlist relationships contain a cycle (or a self-reference).")
        if node in done:
            return
        visiting.add(node)
        for child in parents.get(node, []):
            visit(child)
        visiting.remove(node)
        done.add(node)
        if node in parents:
            order.append(node)

    for parent in parents:
        visit(parent)
    return parents, order, sorted(done)


class Store:
    def __init__(self, path):
        self.path = path
        self.data = read_json(path, {"playlists": {}})
        if not isinstance(self.data.get("playlists"), dict):
            raise SyncError("Invalid state file. Restore a backup; do not discard a pending write.")

    def save(self):
        save_json(self.path, self.data)


class OAuth:
    def __init__(self, client_id, token_path):
        self.client_id = client_id
        self.path = token_path
        self.data = read_json(token_path, {})

    def exchange(self, fields):
        req = Request(TOKEN_URL, data=urlencode(fields).encode(),
                      headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        try:
            with urlopen(req, timeout=30) as response:
                data = json.load(response)
        except HTTPError as exc:
            raise SyncError(f"Spotify authorization failed (HTTP {exc.code}). Run auth again; check Client ID and redirect URI.") from exc
        except (URLError, OSError, http.client.HTTPException, ValueError) as exc:
            raise SyncError("Token request failed. Retry auth/refresh later; no playlist request was sent.", 1) from exc
        if not isinstance(data, dict) or not data.get("access_token"):
            raise SyncError("Spotify returned an invalid token response.")
        refresh = data.get("refresh_token") or self.data.get("refresh_token")
        if not refresh:
            raise SyncError("No refresh token received. Run auth again.")
        scope = data.get("scope", self.data.get("scope", ""))
        if not SCOPES.issubset(set(scope.split())):
            raise SyncError("Required playlist permissions were not granted. Run auth again.")
        self.data = {"client_id": self.client_id, "access_token": data["access_token"],
                     "refresh_token": refresh, "scope": scope,
                     "expires_at": time.time() + float(data.get("expires_in", 3600))}
        save_json(self.path, self.data)

    def token(self, force=False):
        if self.data.get("client_id") != self.client_id or not self.data.get("refresh_token"):
            raise SyncError("Authorize first: python spotify_sync.py auth --config config.json")
        if not SCOPES.issubset(set(self.data.get("scope", "").split())):
            raise SyncError("Cached token lacks playlist permissions. Run auth again.")
        if force or time.time() >= self.data.get("expires_at", 0) - 60:
            self.exchange({"grant_type": "refresh_token", "refresh_token": self.data["refresh_token"],
                           "client_id": self.client_id})
        return self.data["access_token"]

    def authorize(self, redirect_uri, no_browser=False):
        parsed = urlsplit(redirect_uri)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
                or parsed.query or parsed.fragment or parsed.username or parsed.password):
            raise SyncError("This script requires an HTTP IPv4 loopback URI with a port, e.g. http://127.0.0.1:8888/callback")
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        result = {}
        callback_path = parsed.path or "/"

        class Callback(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass  # The callback URL contains a temporary authorization code.

            def do_GET(self):
                query = urlsplit(self.path)
                args = parse_qs(query.query)
                valid_state = secrets.compare_digest(args.get("state", [""])[0], state)
                if query.path != callback_path or not valid_state:
                    self.send_error(400, "Invalid callback")
                    return
                if args.get("error"):
                    result["error"] = "Authorization was denied. Run auth again when ready."
                elif args.get("code"):
                    result["code"] = args["code"][0]
                else:
                    self.send_error(400, "Missing authorization code")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Security-Policy", "default-src 'none'")
                self.end_headers()
                self.wfile.write(b"Spotify authorization received. You can close this tab.")

        url = "https://accounts.spotify.com/authorize?" + urlencode({
            "client_id": self.client_id, "response_type": "code", "redirect_uri": redirect_uri,
            "scope": " ".join(sorted(SCOPES)), "state": state,
            "code_challenge_method": "S256", "code_challenge": challenge, "show_dialog": "true"})
        with HTTPServer(("127.0.0.1", parsed.port), Callback) as server:
            server.timeout = 1
            # Bound stalled connections, and keep authorization interactive only.
            original_get_request = server.get_request

            def bounded_request():
                connection, address = original_get_request()
                connection.settimeout(5)
                return connection, address

            server.get_request = bounded_request
            print("Open this URL on this computer to authorize (do not share it):\n" + url, flush=True)
            if not no_browser:
                webbrowser.open(url)
            deadline = time.monotonic() + 300
            while not result and time.monotonic() < deadline:
                server.handle_request()
        if not result:
            raise SyncError("Authorization timed out after five minutes.")
        if "error" in result:
            raise SyncError(result["error"])
        self.exchange({"grant_type": "authorization_code", "code": result["code"],
                       "redirect_uri": redirect_uri, "client_id": self.client_id, "code_verifier": verifier})
        LOG.info("Authorization saved. Scheduled runs can refresh tokens without a browser.")


class Spotify:
    def __init__(self, oauth, store):
        self.oauth, self.store = oauth, store

    def request(self, method, path, body=None):
        state = self.store.data
        if state.get("quota_blocked"):
            raise SyncError("Spotify quota was exceeded. Reduce scheduling frequency and use resume after quota is available.")
        if state.get("not_before", 0) > time.time():
            raise SyncError(f"Spotify cooldown active for {math.ceil(state['not_before'] - time.time())} more seconds.", 1)
        refreshed = False
        for attempt in range(6):
            token = self.oauth.token()
            req = Request(API + path, method=method,
                          data=None if body is None else json.dumps(body).encode(),
                          headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
            try:
                with urlopen(req, timeout=30) as response:
                    data = json.load(response)
                if not isinstance(data, dict):
                    raise ValueError("Expected JSON object")
                return data
            except HTTPError as exc:
                try:
                    error = json.loads(exc.read()).get("error", {})
                except (ValueError, AttributeError):
                    error = {}
                reason = error.get("reason") if isinstance(error, dict) else None
                if exc.code == 401 and not refreshed:
                    self.oauth.token(force=True)
                    refreshed = True
                    continue
                if exc.code == 429:
                    try:
                        delay = float(exc.headers.get("Retry-After", "5"))
                    except ValueError:
                        delay = 5.0
                    if not math.isfinite(delay) or delay < 0:
                        delay = 5.0
                    state["not_before"] = time.time() + delay
                    if reason == "QUOTA_EXCEEDED":
                        state["quota_blocked"] = True
                    self.store.save()
                    if reason == "QUOTA_EXCEEDED":
                        raise SyncError("Spotify returned QUOTA_EXCEEDED; paused requests. See README recovery instructions.") from exc
                    if delay > 120 or attempt == 5:
                        raise SyncError(f"Spotify rate limited requests; retry after at least {math.ceil(delay)} seconds.", 1) from exc
                    LOG.warning("Rate limited; waiting %.1f seconds.", delay)
                    time.sleep(delay + random.uniform(0.1, 0.5))
                    continue
                if exc.code >= 500:
                    if method != "GET":
                        raise UncertainWrite("Spotify server error during add. A pending batch was saved; rerun sync to check it.") from exc
                    if attempt < 5:
                        time.sleep(min(2 ** attempt, 30) + random.random())
                        continue
                help_text = {
                    401: "Run auth again.",
                    403: "Check Premium, app allowlist, granted scopes, and playlist owner/collaborator access.",
                    404: "Check playlist ID and access. This script uses the current /items endpoints.",
                    400: "Spotify rejected the request. Check playlist/items and current API restrictions."}
                raise SyncError(f"Spotify HTTP {exc.code} for {method} {path.split('?')[0]}. "
                                + help_text.get(exc.code, "Try again later."), 1 if exc.code >= 500 else 2) from exc
            except (URLError, OSError, http.client.HTTPException, ValueError) as exc:
                if method != "GET":
                    raise UncertainWrite("Connection/response failed during add. A pending batch was saved; rerun sync to check it.") from exc
                if attempt == 5:
                    raise SyncError("Could not read Spotify after bounded retries.", 1) from exc
                time.sleep(min(2 ** attempt, 30) + random.random())
        raise SyncError("Retry limit reached.", 1)

    def metadata(self, pid):
        result = self.request("GET", f"/playlists/{pid}?fields=id,name,owner(id),collaborative,snapshot_id")
        if not isinstance(result.get("snapshot_id"), str) or not result["snapshot_id"]:
            raise SyncError(f"Playlist {pid} has no snapshot ID; cannot safely read it.")
        return result

    def read_playlist(self, pid, force_refresh=False):
        for attempt in range(3):
            before = self.metadata(pid)
            cached = self.store.data["playlists"].get(pid)
            if not force_refresh and cached and cached.get("snapshot_id") == before["snapshot_id"]:
                return {**cached, "metadata": before}
            items, skipped, offset = [], 0, 0
            while True:
                query = urlencode({"limit": 50, "offset": offset, "additional_types": "track,episode"})
                page = self.request("GET", f"/playlists/{pid}/items?{query}")
                if not isinstance(page.get("items"), list) or "next" not in page:
                    raise SyncError(f"Invalid playlist contents for {pid}; stopping before writes.")
                for row in page["items"]:
                    if not isinstance(row, dict):
                        raise SyncError("Invalid playlist item object.")
                    # New item field; tolerate legacy response shapes without using legacy endpoints.
                    item = row["item"] if "item" in row else row.get("track")
                    if (not isinstance(item, dict) or row.get("is_local") or item.get("is_local")
                            or not URI_PATTERN.fullmatch(item.get("uri") or "")):
                        skipped += 1
                        continue
                    uri = item["uri"]
                    aliases = [uri]
                    linked = (item.get("linked_from") or {}).get("uri")
                    if linked and URI_PATTERN.fullmatch(linked) and linked not in aliases:
                        aliases.append(linked)
                    items.append({"uri": uri, "aliases": aliases})
                offset += len(page["items"])
                if not page["next"]:
                    break
                if not page["items"]:
                    raise SyncError("Spotify pagination did not advance; stopping.")
            after = self.metadata(pid)
            if before["snapshot_id"] == after["snapshot_id"]:
                result = {"snapshot_id": after["snapshot_id"], "metadata": after,
                          "items": items, "skipped": skipped}
                self.store.data["playlists"][pid] = result
                return result
            LOG.warning("Playlist changed while reading; retrying (%d/3).", attempt + 1)
        raise SyncError("Playlist kept changing while being read. Try again after editing finishes.", 1)


def aliases_of(items):
    return {alias for item in items for alias in item["aliases"]}


def missing_items(existing, candidates):
    seen, missing = aliases_of(existing), []
    for item in candidates:
        if not seen.intersection(item["aliases"]):
            missing.append(item)
        seen.update(item["aliases"])
    return missing


def recover_pending(api, store, acknowledge=False, wait_for_visibility=False):
    pending = store.data.get("pending")
    if not pending:
        if acknowledge:
            LOG.info("No pending write to acknowledge.")
        return
    # Never confirm an addition against a view cached before the request.
    # After a successful response, tolerate a short delay in read visibility.
    # These retries only read playlists: the append is never sent again.
    delays = (0, 2, 5, 10) if wait_for_visibility and not acknowledge else (0,)
    for delay in delays:
        if delay:
            LOG.info("Addition not visible yet; checking again in %d seconds without resending.", delay)
            time.sleep(delay)
        current = api.read_playlist(pending["parent"], force_refresh=True)
        missing = missing_items(current["items"], pending["items"])
        if not missing:
            break
    if missing and not acknowledge:
        raise SyncError(f"Uncertain previous add: {len(missing)} items still absent from parent {pending['parent']}. "
                        "No further writes allowed. Wait, inspect Spotify, then use acknowledge-pending if resolved.")
    store.data.pop("pending", None)
    store.save()
    LOG.info("Previous batch reconciled%s.", "; absent items may be added on the next sync" if missing else "")


def sync(api, store, parents, order, all_ids, dry_run=False, include_episodes=False):
    recover_pending(api, store)
    profile = api.request("GET", "/me")
    user_id = profile.get("id")
    if not user_id:
        raise SyncError("Spotify did not return the current user ID.")
    # Preflight all reads and likely write permissions before the first add.
    views = {pid: api.read_playlist(pid) for pid in all_ids}
    for pid in order:
        meta = views[pid]["metadata"]
        if (meta.get("owner") or {}).get("id") != user_id and not meta.get("collaborative"):
            raise SyncError(f"Parent {pid} is neither owned by you nor collaborative.")
    total = 0
    for pid in order:
        candidates = [item for child in parents[pid] for item in views[child]["items"]
                      if include_episodes or item["uri"].startswith("spotify:track:")]
        current = views[pid] if dry_run else api.read_playlist(pid)
        missing = missing_items(current["items"], candidates)
        LOG.info("Parent %s: %d missing items%s.", pid, len(missing), " (preview)" if dry_run else "")
        if dry_run:
            for item in missing:
                LOG.info("Would add %s to %s", item["uri"], pid)
            views[pid] = {**current, "items": current["items"] + missing}
            total += len(missing)
            continue
        # Refresh before every batch to reduce races with edits from other apps/users.
        appended = set()
        while missing:
            current = api.read_playlist(pid)
            missing = [item for item in missing_items(current["items"], candidates)
                       if not appended.intersection(item["aliases"])]
            if not missing:
                break
            batch = missing[:100]
            api.oauth.token()  # Refresh before recording a possible playlist write.
            store.data["pending"] = {"parent": pid, "items": batch, "started_at": time.time()}
            store.save()
            try:
                api.request("POST", f"/playlists/{pid}/items", {"uris": [item["uri"] for item in batch]})
            except UncertainWrite:
                raise
            except SyncError:
                # A definite rejection (e.g. 403 or 429) did not append the batch.
                store.data.pop("pending", None)
                store.save()
                raise
            # Keep journal until a fresh, consistent read confirms the append.
            recover_pending(api, store, wait_for_visibility=True)
            appended.update(aliases_of(batch))
            total += len(batch)
            LOG.info("Confirmed %d additions to %s.", len(batch), pid)
            current = api.read_playlist(pid)
            missing = [item for item in missing_items(current["items"], candidates)
                       if not appended.intersection(item["aliases"])]
        views[pid] = api.read_playlist(pid)
    for pid in all_ids:
        if views[pid].get("skipped"):
            LOG.warning("Playlist %s: skipped %d local/null/unsupported entries.", pid, views[pid]["skipped"])
    store.save()
    LOG.info("%s complete: %d %s.", "Preview" if dry_run else "Sync", total,
             "proposed additions" if dry_run else "confirmed additions")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["auth", "sync", "acknowledge-pending", "resume"])
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"),
                        help="Committable playlist relationships JSON")
    parser.add_argument("--credentials", type=Path,
                        help="Private app credentials JSON (default: credentials.json beside --config)")
    parser.add_argument("--dry-run", action="store_true", help="Read and preview; no playlist writes")
    parser.add_argument("--watch", type=int, metavar="SECONDS", help="Repeat sync; minimum 300 seconds")
    parser.add_argument("--no-browser", action="store_true", help="Print auth URL without opening it")
    parser.add_argument("--log-file", type=Path, help="Append logs to this file (no token logging)")
    args = parser.parse_args(argv)
    handlers = [logging.StreamHandler()] if sys.stderr is not None else []
    if args.log_file:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(args.log_file, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)
    try:
        if args.watch is not None and (args.command != "sync" or args.watch < 300):
            raise SyncError("--watch is only for sync and must be at least 300 seconds.")
        config_path = args.config.resolve()
        config, credentials = load_settings(config_path, args.credentials.resolve() if args.credentials else None)
        parents, order, all_ids = relationships(config)
        client_id = credentials["client_id"]
        if type(config.get("include_episodes", False)) is not bool:
            raise SyncError("include_episodes must be true or false.")
        # One state directory and lock per project, shared by all its configurations.
        state_dir = config_path.parent / ".spotify-sync"
        with exclusive_lock(state_dir / "run.lock"):
            oauth = OAuth(client_id, state_dir / "token.json")
            store = Store(state_dir / "state.json")
            api = Spotify(oauth, store)
            if args.command == "auth":
                # Never associate a previous account's cached contents with a new login.
                if store.data.get("pending"):
                    raise SyncError("Resolve the pending write with the existing login before reauthorizing.")
                store.data["playlists"] = {}
                store.save()
                oauth.authorize(credentials.get("redirect_uri", "http://127.0.0.1:8888/callback"), args.no_browser)
                return 0
            if args.command == "resume":
                store.data.pop("quota_blocked", None)
                # Retry-After still applies; never erase Spotify's timed cooldown.
                store.save()
                LOG.info("Quota pause cleared. Timed cooldowns and pending writes still apply.")
                return 0
            if args.command == "acknowledge-pending":
                recover_pending(api, store, acknowledge=True)
                return 0
            while True:
                try:
                    sync(api, store, parents, order, all_ids, args.dry_run, config.get("include_episodes", False))
                except SyncError as exc:
                    if not args.watch or exc.code != 1:
                        raise
                    LOG.error("%s", exc)
                if not args.watch:
                    return 0
                LOG.info("Next check in %d seconds. Ctrl+C to stop.", args.watch)
                time.sleep(args.watch)
    except SyncError as exc:
        LOG.error("%s", exc)
        return exc.code
    except (OSError, ValueError, KeyError, TypeError) as exc:
        LOG.error("Local configuration/state error: %s", exc)
        return 2
    except KeyboardInterrupt:
        LOG.info("Stopped. Any in-flight batch will be checked on the next run.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
