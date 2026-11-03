# Geni access investigation — 2026-11-03

**Authenticated read-only access was not demonstrated.** No OAuth login,
code exchange, token refresh, profile request, or profile mutation was attempted.

## Findings

Reviewed `tools/geni_import.py`, repository file inventory, `README.md`, and
`.gitignore` on `main`. There is no authorization-URL builder or callback
listener in this repository. The importer accepts an externally obtained code
(`auth --code` or `GENI_AUTH_CODE`); its docstring also suggests an incomplete
client-side authorization URL. The original browser URL and its decoded
`redirect_uri` are unavailable, so their construction outside this repository
cannot be reconstructed.

`GENI_APP_ID` defaults to 2290. `GENI_APP_SECRET` is required for code exchange
and refresh. `GENI_REDIRECT_URI` is optional in code exchange only; refresh
requests currently omit it. `GENI_ACCESS_TOKEN` overrides the local token file;
`GENI_REFRESH_TOKEN` can bootstrap that file. Tokens are stored at
`~/.geni/token.json`.

The support explanation supplied in the assignment (ticket #203513, Mike,
October 19, 2026) makes localhost rejection a plausible cause of the original
failure. It is not independently confirmed. Changing the exchange parameter
alone cannot change the browser URL. Application 2290's registered Site Domain
and Callback URL could not be accessed; **callback equality and domain
compatibility remain unverified**.

The current managed environment has an enforced restricted network policy:
Geni is absent from its allowed destinations. No secrets or runtime variables
are bound. All six importer GENI variables above (including GENI_AUTH_CODE)
are unset, and the local token file is absent. The selected environment therefore
cannot currently complete the OAuth flow. A hostname mapping alone does not
grant network access or provide a working callback receiver.

## Current documentation

Checked official [OAuth introduction](https://www.geni.com/platform/developer/help/oauth_intro)
and [server-side flow](https://www.geni.com/platform/developer/help/oauth_server_side?version=1).
Authorization uses `/platform/oauth/authorize`; code exchange uses
`/platform/oauth/request_token`. The redirect must be within the registered
Site Domain and the exchange redirect must match the authorization request.
The docs specify a redirect for refresh as well. They document `state` for
CSRF protection and show `read_profile` as a scope. Request read access explicitly
and verify the consent screen; omitted scope defaults to full access.
Bearer headers are recommended over token query parameters.

## Owner handoff — stop before human authorization

1. In Geni's developer application settings, inspect app 2290's Site Domain and
   Callback URL. Compare them with the **decoded redirect_uri in the original
   browser URL**, without sharing codes, tokens, or full callback URLs.
2. Choose an owner-controlled hostname and callback receiver. For local use,
   follow support's hosts-file suggestion on the machine running the browser:
   map that hostname to loopback and run the receiver there. Use a hostname
   consistent with the app settings; confirm scheme, port, and path. A hosts
   entry on a remote Codex machine does not configure the owner's browser.
3. Configure that same redirect in the initial URL and `GENI_REDIRECT_URI`.
   Use client_id=2290, response_type=code, scope=read_profile, and a fresh
   unpredictable state verified by the receiver. The receiver must suppress
   query logging. This repository does not implement that receiver.
4. If continuing in Codex, allow `www.geni.com` via the supported environment
   network configuration and provide credentials through secure secret bindings.
   Do not disable the proxy or TLS verification.
5. **Human step:** the owner opens the corrected authorization URL, logs in,
   and reviews read-only consent. Stop for the owner here; do not automate login
   or CAPTCHA. Never paste the resulting code or token into a PR or chat.
   Exchange the code promptly on the trusted machine using `GENI_AUTH_CODE`
   rather than a command-line argument, with the secret securely configured.
6. If Geni still blocks the browser request, privately supply the blocked-page
   IP address and Incident ID to support under ticket #203513. Neither is
   available from this investigation; a local network denial is not a Geni
   firewall incident.

After authorization, the recommended acceptance check is one
`GET https://www.geni.com/api/profile?fields=id` with an Authorization Bearer
header. Discard the returned identifier and log only HTTP status and whether
a nonempty id was returned. A documentation fetch or successful code exchange
does not satisfy this acceptance check.

## Security, changes, and validation

This PR adds this report only. Importer behavior, GEDCOM functionality, app
registration, and environment configuration are unchanged.

Existing importer cautions: `whoami` prints a name and profile id; `path` and
`run` print family details. API errors include a response-body excerpt and token
errors include server descriptions. Avoid these outputs in shared logs.
Token saving applies mode 0600 after writing; an atomic write with restrictive
permissions from creation would be preferable before broader deployment.
The existing ignore rules cover `.env`, `token.json`, and `*.ged`; ignore rules
are not a substitute for inspecting a proposed commit.

Validation: importer syntax compilation and CLI help passed. A synthetic GEDCOM
parent/child smoke check passed without network access. File inventory confirms
no repository OAuth URL builder, callback listener, tests, or AGENTS.md.
Credential checks reported presence only, never values. Git clone failed because
the configured proxy was unreachable; source inspection used the GitHub connector.
The proposed commit contains only this report, with no credentials, profile
payloads, family records, or raw authentication URLs. No historical secret audit
is claimed.

**Recommended next step:** owner verifies app settings and establishes the
callback on a trusted machine, then completes human authorization. Resume with
one redacted read-only acceptance check. Continue using GEDCOM offline meanwhile.
