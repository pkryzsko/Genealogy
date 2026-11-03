"""Offline OAuth contract and GEDCOM regression tests; all credentials are synthetic."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse
import warnings

spec = importlib.util.spec_from_file_location(
    "geni_import", Path(__file__).resolve().parents[1] / "tools/geni_import.py")
geni = importlib.util.module_from_spec(spec)
spec.loader.exec_module(geni)


class OAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.addCleanup(patch.stopall)
        patch.object(geni, "STATE_FILE", root / "oauth-state.json").start()
        patch.object(geni, "TOKEN_FILE", root / "token.json").start()
        patch.dict(os.environ, {
            "GENI_APP_SECRET": "synthetic-secret",
            "GENI_REDIRECT_URI": "https://callback.example.test/oauth/return",
        }, clear=True).start()
        # Any unexpected network request is a test failure.
        self.net = patch.object(geni.urllib.request, "urlopen",
                                side_effect=AssertionError("unexpected network access")).start()

    def begin(self):
        return urllib.parse.parse_qs(urllib.parse.urlsplit(geni.authorization_url()).query)

    def response(self, body):
        response = io.StringIO(json.dumps(body))
        response.headers = {"X-API-Rate-Remaining": "10"}
        self.net.side_effect = None
        self.net.return_value = response

    def test_endpoints_scope_and_random_state(self):
        first = self.begin()
        second = self.begin()
        self.assertEqual(geni.AUTHORIZE_URL, "https://www.geni.com/platform/oauth/authorize")
        self.assertEqual(geni.TOKEN_URL, "https://www.geni.com/platform/oauth/request_token")
        self.assertEqual(first["client_id"], ["2290"])
        self.assertEqual(first["response_type"], ["code"])
        self.assertEqual(first["scope"], ["read_profile"])
        self.assertNotEqual(first["state"], second["state"])
        self.assertGreaterEqual(len(first["state"][0]), 40)
        self.assertEqual(geni.STATE_FILE.stat().st_mode & 0o777, 0o600)

    def test_missing_invalid_and_localhost_redirect_fail_without_network(self):
        for value in ("", "relative", "https://", "ftp://callback.example.test/",
                      "http://localhost:8000/", "http://sub.localhost./",
                      "https://user:password@callback.example.test/",
                      "https://callback.example.test/#fragment",
                      "https://callback.example.test/?code=unexpected"):
            with self.subTest(value=value):
                os.environ["GENI_REDIRECT_URI"] = value
                with self.assertRaises(SystemExit):
                    geni.authorization_url()
                with self.assertRaises(SystemExit):
                    geni.exchange_code("synthetic-code", "synthetic-state")
        self.net.assert_not_called()

    def test_exchange_exact_redirect_post_and_private_token(self):
        os.environ["GENI_REDIRECT_URI"] = "https://callback.example.test:8443/OAuth/%2freturn/"
        query = self.begin()
        self.response({"access_token": "synthetic-access", "refresh_token": "synthetic-refresh",
                       "expires_in": 3600})
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            geni.exchange_code("synthetic-code", query["state"][0])
        req = self.net.call_args.args[0]
        params = urllib.parse.parse_qs(req.data.decode())
        self.assertEqual(req.full_url, geni.TOKEN_URL)
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(params["redirect_uri"], query["redirect_uri"])
        self.assertEqual(params["grant_type"], ["authorization_code"])
        self.assertNotIn("synthetic-", output.getvalue())
        self.assertFalse(geni.STATE_FILE.exists())
        self.assertEqual(geni.TOKEN_FILE.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(SystemExit):
            geni.exchange_code("synthetic-code", query["state"][0])
        self.assertEqual(self.net.call_count, 1)

    def test_state_missing_wrong_expired_and_replaced(self):
        with self.assertRaises(SystemExit):
            geni.exchange_code("synthetic-code", "no-session")
        old = self.begin()["state"][0]
        current = self.begin()["state"][0]
        for state in (None, "", "wrong-state", "non-ascii-\u00e9", old):
            with self.assertRaises(SystemExit):
                geni.exchange_code("synthetic-code", state)
        with patch.object(geni.time, "time", return_value=0):
            with self.assertRaises(SystemExit):
                geni.exchange_code("synthetic-code", current)
        pending = json.loads(geni.STATE_FILE.read_text())
        with patch.object(geni.time, "time", return_value=pending["created_at"] + geni.STATE_TTL):
            with self.assertRaises(SystemExit):
                geni.exchange_code("synthetic-code", current)
        self.net.assert_not_called()

    def test_redirect_or_client_change_rejected(self):
        state = self.begin()["state"][0]
        for variable, value in (("GENI_REDIRECT_URI", "https://callback.example.test/other"),
                                ("GENI_APP_ID", "9999")):
            with patch.dict(os.environ, {variable: value}):
                with self.assertRaises(SystemExit):
                    geni.exchange_code("synthetic-code", state)
        self.net.assert_not_called()

    def test_exchange_error_consumes_state_and_redacts_body(self):
        state = self.begin()["state"][0]
        self.net.side_effect = urllib.error.HTTPError(
            geni.TOKEN_URL, 400, "synthetic-private-message", {}, io.BytesIO(b"synthetic-private-body"))
        with self.assertRaises(SystemExit) as error:
            geni.exchange_code("synthetic-code", state)
        self.assertEqual(str(error.exception), "Token request failed: HTTP 400")
        self.assertFalse(geni.STATE_FILE.exists())

    def test_token_json_error_redacted(self):
        self.response({"error_description": "synthetic-private-body"})
        with self.assertRaises(SystemExit) as error:
            geni.token_request({"redirect_uri": os.environ["GENI_REDIRECT_URI"]})
        self.assertNotIn("synthetic-private", str(error.exception))
        self.assertFalse(geni.TOKEN_FILE.exists())

    def test_refresh_includes_original_redirect(self):
        geni.save_token({"access_token": "synthetic-old", "refresh_token": "synthetic-refresh",
                         "expires_in": 0, "redirect_uri": os.environ["GENI_REDIRECT_URI"]})
        self.response({"access_token": "synthetic-new", "expires_in": 3600})
        self.assertEqual(geni.access_token(), "synthetic-new")
        params = urllib.parse.parse_qs(self.net.call_args.args[0].data.decode())
        self.assertEqual(params["redirect_uri"], [os.environ["GENI_REDIRECT_URI"]])
        self.assertEqual(params["grant_type"], ["refresh_token"])

    def test_refresh_rejects_changed_redirect(self):
        geni.save_token({"access_token": "synthetic-old", "refresh_token": "synthetic-refresh",
                         "expires_in": 0, "redirect_uri": "https://other.example.test/"})
        with self.assertRaises(SystemExit):
            geni.access_token()
        self.net.assert_not_called()

    def test_env_refresh_requires_redirect(self):
        os.environ["GENI_REFRESH_TOKEN"] = "synthetic-refresh"
        os.environ.pop("GENI_REDIRECT_URI")
        with self.assertRaises(SystemExit):
            geni.access_token()
        self.net.assert_not_called()

    def test_existing_access_token_needs_no_oauth_config(self):
        os.environ.clear()
        os.environ["GENI_ACCESS_TOKEN"] = "synthetic-access"
        self.assertEqual(geni.access_token(), "synthetic-access")
        self.net.assert_not_called()

    def test_check_uses_readonly_get_and_hides_identity(self):
        os.environ["GENI_ACCESS_TOKEN"] = "synthetic-access"
        self.response({"id": "synthetic-private-id", "name": "synthetic-private-name"})
        output = io.StringIO()
        with patch.object(geni.sys, "argv", ["geni_import.py", "check"]), contextlib.redirect_stdout(output):
            geni.main()
        req = self.net.call_args.args[0]
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(req.full_url, geni.API + "/profile?fields=id")
        self.assertEqual(req.get_header("Authorization"), "Bearer synthetic-access")
        self.assertNotIn("synthetic-", output.getvalue())
        self.assertIn("succeeded", output.getvalue())

    def test_check_rejects_missing_identity(self):
        os.environ["GENI_ACCESS_TOKEN"] = "synthetic-access"
        self.response({})
        with patch.object(geni.sys, "argv", ["geni_import.py", "check"]):
            with self.assertRaises(SystemExit):
                geni.main()

    def test_api_error_body_redacted(self):
        os.environ["GENI_ACCESS_TOKEN"] = "synthetic-access"
        self.net.side_effect = urllib.error.HTTPError(
            geni.API, 403, "synthetic-private", {}, io.BytesIO(b"synthetic-private-body"))
        with self.assertRaises(SystemExit) as error:
            geni.Geni().get("profile", fields="id")
        self.assertEqual(str(error.exception), "Geni GET failed: HTTP 403")

    def test_hidden_input_never_falls_back_to_echo(self):
        def unavailable(prompt):
            warnings.warn("synthetic-warning", geni.getpass.GetPassWarning)
            self.fail("must stop before echoed input")
        with patch.object(geni.getpass, "getpass", side_effect=unavailable):
            with self.assertRaises(SystemExit):
                geni.hidden_input("Code: ")

    def test_auth_noninteractive_requires_both_values(self):
        with patch.object(geni.sys, "argv", ["geni_import.py", "auth"]), \
                patch.object(geni.sys.stdin, "isatty", return_value=False):
            with self.assertRaises(SystemExit):
                geni.main()
        self.net.assert_not_called()

    def test_auth_prompts_for_returned_code_and_state(self):
        state = self.begin()["state"][0]
        self.response({"access_token": "synthetic-access", "expires_in": 3600})
        with patch.object(geni.sys, "argv", ["geni_import.py", "auth"]), \
                patch.object(geni.sys.stdin, "isatty", return_value=True), \
                patch.object(geni, "hidden_input", side_effect=["synthetic-code", state]), \
                contextlib.redirect_stdout(io.StringIO()):
            geni.main()
        self.assertEqual(self.net.call_count, 1)

    def test_synthetic_gedcom_works_without_auth(self):
        os.environ.clear()
        path = Path(self.tmp.name) / "synthetic.ged"
        path.write_text("0 @I1@ INDI\n1 NAME Example /Child/\n1 FAMC @F1@\n"
                        "0 @I2@ INDI\n1 NAME Example /Parent/\n1 FAMS @F1@\n"
                        "0 @F1@ FAM\n1 WIFE @I2@\n1 CHIL @I1@\n")
        source = geni.Gedcom(path)
        self.assertEqual(source.family("gedcom-I1"), (["gedcom-I2"], []))
        self.net.assert_not_called()


if __name__ == "__main__":
    unittest.main()
