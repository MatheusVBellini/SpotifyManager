import copy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import spotify_sync as s

A, B, C, D = (char * 22 for char in "ABCD")


def track(char, kind="track"):
    uri = f"spotify:{kind}:{char * 22}"
    return {"uri": uri, "aliases": [uri]}


class FakeOAuth:
    def __init__(self):
        self.calls = []

    def token(self, force=False):
        self.calls.append(force)
        return "test-token"


class FakeAPI:
    def __init__(self, store, contents):
        self.store = store
        self.oauth = FakeOAuth()
        self.contents = copy.deepcopy(contents)
        self.posts = []
        self.fail_read = None
        self.fail_post = None

    def read_playlist(self, pid):
        if pid == self.fail_read:
            raise s.SyncError("inaccessible")
        return {"items": copy.deepcopy(self.contents[pid]), "skipped": 0,
                "metadata": {"owner": {"id": "me"}, "collaborative": False}}

    def request(self, method, path, body=None):
        if path == "/me":
            return {"id": "me"}
        assert method == "POST" and path.endswith("/items")
        pid = path.split("/")[2]
        self.posts.append((pid, copy.deepcopy(body["uris"])))
        if self.fail_post == "reject":
            raise s.SyncError("403")
        if self.fail_post != "uncertain-absent":
            self.contents[pid].extend({"uri": uri, "aliases": [uri]} for uri in body["uris"])
        if self.fail_post and self.fail_post.startswith("uncertain"):
            raise s.UncertainWrite("timeout")
        return {"snapshot_id": str(len(self.posts))}


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = s.Store(Path(self.temp.name) / "state.json")

    def run_sync(self, api, rows, dry=False, episodes=False):
        parents, order, ids = s.relationships({"relationships": rows})
        s.sync(api, self.store, parents, order, ids, dry, episodes)

    def test_nested_propagation_and_idempotence(self):
        # Deliberately list ancestor first; overlap and child duplicates.
        api = FakeAPI(self.store, {A: [track("x")], B: [track("y"), track("y")],
                                  C: [track("z"), track("y")], D: [track("x")]})
        rows = [{"parent": A, "children": [B, D]}, {"parent": B, "children": [C]}]
        self.run_sync(api, rows)
        self.assertEqual(api.posts, [(B, [track("z")["uri"]]),
                                     (A, [track("y")["uri"], track("z")["uri"]])])
        self.run_sync(api, rows)
        self.assertEqual(len(api.posts), 2)

    def test_dry_run_propagates_without_writes_or_cache_pollution(self):
        api = FakeAPI(self.store, {A: [], B: [], C: [track("z")]})
        rows = [{"parent": A, "children": [B]}, {"parent": B, "children": [C]}]
        with self.assertLogs(s.LOG, "INFO") as logs:
            self.run_sync(api, rows, dry=True)
        self.assertIn("2 proposed additions", "\n".join(logs.output))
        self.assertEqual(api.posts, [])
        self.assertEqual(api.contents[A], [])
        self.assertEqual(self.store.data["playlists"], {})

    def test_batching_and_episode_option(self):
        tracks = [{"uri": f"spotify:track:{n:022d}", "aliases": [f"spotify:track:{n:022d}"]} for n in range(205)]
        api = FakeAPI(self.store, {A: [], B: tracks + [track("p", "episode")]})
        self.run_sync(api, [{"parent": A, "children": [B]}])
        self.assertEqual([len(post[1]) for post in api.posts], [100, 100, 5])
        self.run_sync(api, [{"parent": A, "children": [B]}], episodes=True)
        self.assertEqual(api.posts[-1][1], [track("p", "episode")["uri"]])

    def test_preflight_failure_does_not_write(self):
        api = FakeAPI(self.store, {A: [], B: [track("x")], C: []})
        api.fail_read = C
        with self.assertRaises(s.SyncError):
            self.run_sync(api, [{"parent": A, "children": [B, C]}])
        self.assertFalse(api.posts)

    def test_uncertain_accepted_write_recovers_without_duplicate(self):
        api = FakeAPI(self.store, {A: [], B: [track("x")]})
        api.fail_post = "uncertain-accepted"
        rows = [{"parent": A, "children": [B]}]
        with self.assertRaises(s.UncertainWrite):
            self.run_sync(api, rows)
        self.assertIn("pending", s.read_json(self.store.path))
        api.fail_post = None
        self.run_sync(api, rows)
        self.assertEqual(len(api.posts), 1)
        self.assertNotIn("pending", self.store.data)

    def test_uncertain_absent_write_blocks_until_acknowledged(self):
        api = FakeAPI(self.store, {A: [], B: [track("x")]})
        api.fail_post = "uncertain-absent"
        rows = [{"parent": A, "children": [B]}]
        with self.assertRaises(s.UncertainWrite):
            self.run_sync(api, rows)
        api.fail_post = None
        with self.assertRaises(s.SyncError):
            self.run_sync(api, rows)
        self.assertEqual(len(api.posts), 1)
        s.recover_pending(api, self.store, acknowledge=True)
        self.run_sync(api, rows)
        self.assertEqual(len(api.posts), 2)

    def test_definite_rejection_clears_pending(self):
        api = FakeAPI(self.store, {A: [], B: [track("x")]})
        api.fail_post = "reject"
        with self.assertRaises(s.SyncError):
            self.run_sync(api, [{"parent": A, "children": [B]}])
        self.assertNotIn("pending", self.store.data)

    def test_partial_uncertain_batch_does_not_resend(self):
        api = FakeAPI(self.store, {A: [track("x")], B: [track("x"), track("y")]})
        self.store.data["pending"] = {"parent": A, "items": [track("x"), track("y")]}
        self.store.save()
        with self.assertRaises(s.SyncError):
            self.run_sync(api, [{"parent": A, "children": [B]}])
        self.assertEqual(api.posts, [])
        self.assertIn("pending", self.store.data)

    def test_cycles_and_url_parsing(self):
        self.assertEqual(s.playlist_id(f"https://open.spotify.com/intl-br/playlist/{A}?si=123"), A)
        self.assertEqual(s.playlist_id(f"spotify:playlist:{A}"), A)
        with self.assertRaises(s.SyncError):
            s.relationships({"relationships": [{"parent": A, "children": [B]}, {"parent": B, "children": [A]}]})
        with self.assertRaises(s.SyncError):
            s.playlist_id("invalid")

    def test_relink_aliases(self):
        original, alternative = track("a"), track("b")
        alternative["aliases"].append(original["uri"])
        self.assertEqual(s.missing_items([alternative], [original]), [])

    def test_lock_excludes_second_instance_and_releases(self):
        lock = Path(self.temp.name) / "lock"
        with s.exclusive_lock(lock):
            with self.assertRaises(s.SyncError):
                with s.exclusive_lock(lock):
                    pass
        with s.exclusive_lock(lock):
            pass


def response(data):
    return io.BytesIO(json.dumps(data).encode())


def http_error(code, data=None, headers=None):
    return HTTPError("https://api.spotify.com/test", code, "test", headers or {},
                     response(data or {"error": {"status": code}}))


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = s.Store(Path(self.temp.name) / "state.json")
        self.oauth = FakeOAuth()
        self.api = s.Spotify(self.oauth, self.store)

    def test_401_refreshes_once(self):
        with patch.object(s, "urlopen", side_effect=[http_error(401), response({"id": "me"})]):
            self.assertEqual(self.api.request("GET", "/me"), {"id": "me"})
        self.assertIn(True, self.oauth.calls)

    def test_read_5xx_retries(self):
        with patch.object(s, "urlopen", side_effect=[http_error(503), response({"ok": True})]) as request, patch.object(s.time, "sleep"):
            self.assertTrue(self.api.request("GET", "/me")["ok"])
            self.assertEqual(request.call_count, 2)

    def test_append_network_and_5xx_never_retry(self):
        for error in [URLError("timeout"), http_error(503)]:
            with patch.object(s, "urlopen", side_effect=error) as request:
                with self.assertRaises(s.UncertainWrite):
                    self.api.request("POST", f"/playlists/{A}/items", {"uris": [track("x")["uri"]]})
                self.assertEqual(request.call_count, 1)

    def test_429_honors_header_before_retry(self):
        with patch.object(s, "urlopen", side_effect=[http_error(429, headers={"Retry-After": "3"}), response({"ok": True})]), patch.object(s.time, "sleep") as sleep:
            self.api.request("GET", "/me")
            self.assertGreaterEqual(sleep.call_args[0][0], 3)

    def test_long_cooldown_persists_and_blocks_next_run(self):
        with patch.object(s, "urlopen", side_effect=http_error(429, headers={"Retry-After": "500"})):
            with self.assertRaises(s.SyncError):
                self.api.request("GET", "/me")
        with patch.object(s, "urlopen") as request:
            with self.assertRaises(s.SyncError):
                self.api.request("GET", "/me")
            request.assert_not_called()
        self.assertIn("not_before", s.read_json(self.store.path))

    def test_quota_pause_survives_process_restart(self):
        error = http_error(429, {"error": {"reason": "QUOTA_EXCEEDED"}})
        with patch.object(s, "urlopen", side_effect=error):
            with self.assertRaises(s.SyncError) as caught:
                self.api.request("GET", "/me")
            self.assertEqual(caught.exception.code, 2)
        restarted = s.Spotify(self.oauth, s.Store(self.store.path))
        with patch.object(s, "urlopen") as request:
            with self.assertRaises(s.SyncError):
                restarted.request("GET", "/me")
            request.assert_not_called()

    def test_pagination_new_and_old_item_shapes_and_cache(self):
        metadata = {"snapshot_id": "one", "owner": {"id": "me"}}
        page1 = {"items": [{"item": {"uri": track("a")["uri"]}}, {"item": None},
                            {"item": {"uri": "spotify:local:a:b:c", "is_local": True}}], "next": "yes"}
        page2 = {"items": [{"track": {"uri": track("b")["uri"]}}], "next": None}
        replies = [metadata, page1, page2, metadata, metadata]
        with patch.object(self.api, "request", side_effect=replies) as request:
            result = self.api.read_playlist(A)
            self.assertEqual(len(result["items"]), 2)
            self.assertEqual(result["skipped"], 2)
            self.assertIn("offset=3", request.call_args_list[2].args[1])
            self.assertIn("limit=50", request.call_args_list[1].args[1])
            self.api.read_playlist(A)
            self.assertEqual(request.call_count, 5)

    def test_snapshot_change_restarts_read(self):
        page = {"items": [{"item": {"uri": track("a")["uri"]}}], "next": None}
        with patch.object(self.api, "request", side_effect=[{"snapshot_id": "1"}, page, {"snapshot_id": "2"},
                                                           {"snapshot_id": "2"}, page, {"snapshot_id": "2"}]) as request:
            self.assertEqual(self.api.read_playlist(A)["snapshot_id"], "2")
            self.assertEqual(request.call_count, 6)

    def test_refresh_preserves_refresh_token_when_not_rotated(self):
        token_path = Path(self.temp.name) / "token.json"
        data = {"client_id": "a" * 32, "refresh_token": "old-refresh", "access_token": "expired",
                "scope": " ".join(s.SCOPES), "expires_at": 0}
        s.save_json(token_path, data)
        oauth = s.OAuth("a" * 32, token_path)
        with patch.object(s, "urlopen", return_value=response({"access_token": "fresh", "expires_in": 3600})):
            self.assertEqual(oauth.token(), "fresh")
        self.assertEqual(s.read_json(token_path)["refresh_token"], "old-refresh")


class AuthorizationTests(unittest.TestCase):
    def test_pkce_state_and_token_exchange(self):
        captured = {}
        rejected = Mock()

        class FakeServer:
            def __init__(self, address, handler):
                captured["address"] = address
                self.handler = handler

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def get_request(self):
                raise AssertionError("No real socket is used in this test")

            def handle_request(self):
                args = captured["authorize"]
                for state in ["invalid", args["state"][0]]:
                    fake = SimpleNamespace(path="/callback?" + s.urlencode({"state": state, "code": "test-code"}),
                                           send_error=rejected, send_response=Mock(), send_header=Mock(),
                                           end_headers=Mock(), wfile=io.BytesIO())
                    self.handler.do_GET(fake)

        def open_browser(url):
            captured["authorize"] = s.parse_qs(s.urlsplit(url).query)
            return True

        def token_request(req, timeout):
            captured["token"] = s.parse_qs(req.data.decode())
            return response({"access_token": "test-access", "refresh_token": "test-refresh",
                             "scope": " ".join(s.SCOPES), "expires_in": 3600})

        with tempfile.TemporaryDirectory() as directory:
            oauth = s.OAuth("a" * 32, Path(directory) / "token.json")
            with patch.object(s, "HTTPServer", FakeServer), patch.object(s.webbrowser, "open", open_browser), patch.object(s, "urlopen", token_request), patch("builtins.print"):
                oauth.authorize("http://127.0.0.1:8888/callback")
            self.assertEqual(captured["address"], ("127.0.0.1", 8888))
            rejected.assert_called_once()
            verifier = captured["token"]["code_verifier"][0]
            challenge = s.base64.urlsafe_b64encode(s.hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
            self.assertEqual(captured["authorize"]["code_challenge"][0], challenge)
            self.assertEqual(captured["token"]["code"][0], "test-code")
            self.assertEqual(oauth.data["refresh_token"], "test-refresh")

    def test_localhost_rejected_before_starting_listener(self):
        with tempfile.TemporaryDirectory() as directory:
            oauth = s.OAuth("a" * 32, Path(directory) / "token.json")
            with patch.object(s, "HTTPServer") as server:
                with self.assertRaises(s.SyncError):
                    oauth.authorize("http://localhost:8888/callback")
                server.assert_not_called()


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config_path = self.root / "config.json"
        self.config = {"include_episodes": False, "relationships": [{"parent": A, "children": [B]}]}
        self.credentials = {"client_id": "a" * 32, "redirect_uri": "http://127.0.0.1:8888/callback"}
        s.save_json(self.config_path, self.config)
        s.save_json(self.root / "credentials.json", self.credentials)

    def test_credentials_default_to_config_directory(self):
        # Independent of the terminal's current working directory.
        config, credentials = s.load_settings(self.config_path)
        self.assertEqual(config, self.config)
        self.assertEqual(credentials, self.credentials)
        self.assertNotIn("client_id", config)

    def test_explicit_credentials_path(self):
        custom = self.root / "private" / "credentials.json"
        other = {**self.credentials, "client_id": "b" * 32}
        s.save_json(custom, other)
        _, credentials = s.load_settings(self.config_path, custom)
        self.assertEqual(credentials, other)

    def test_credentials_in_public_config_are_rejected_without_exposing_value(self):
        for key in ["client_id", "client_secret", "api_key", "access_token", "refresh_token"]:
            s.save_json(self.config_path, {**self.config, key: "PRIVATE_VALUE"})
            with self.assertRaises(s.SyncError) as caught:
                s.load_settings(self.config_path)
            self.assertNotIn("PRIVATE_VALUE", str(caught.exception))

    def test_missing_credentials_has_setup_instruction(self):
        with self.assertRaises(s.SyncError) as caught:
            s.load_settings(self.config_path, self.root / "missing-credentials.json")
        self.assertIn("credentials.example.json", str(caught.exception))

    def test_auth_command_reads_private_app_settings(self):
        with patch.object(s.OAuth, "authorize") as authorize:
            result = s.main(["auth", "--config", str(self.config_path), "--no-browser"])
        self.assertEqual(result, 0)
        authorize.assert_called_once_with(self.credentials["redirect_uri"], True)

    def test_invalid_client_id_fails_before_authorization(self):
        s.save_json(self.root / "credentials.json", {"client_id": "INVALID_PRIVATE_VALUE"})
        with patch.object(s.OAuth, "authorize") as authorize, self.assertLogs(s.LOG, "ERROR") as logs:
            result = s.main(["auth", "--config", str(self.config_path)])
        self.assertEqual(result, 2)
        authorize.assert_not_called()
        self.assertNotIn("INVALID_PRIVATE_VALUE", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
