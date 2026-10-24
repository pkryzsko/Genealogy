# Geni OAuth access: support response and Devin handoff

Updated: 2026-10-24
Status: support guidance received; connection not retested in this handoff.

## Reacquaintenment

Patrick reported that authorizing his registered Geni application to read his own tree was blocked at the OAuth authorization page. The original report was sent on 17 October 2026 after an earlier failed attempt and a wait of more than 24 hours.

Geni application ID: 2290 (also the existing importer's default).

Source: Mike at Geni Customer Support, email dated 19 October 2026, subject “[Geni Help Center] Re: Getting access denied,” ticket [203513](https://help.geni.com/hc/requests/203513). The ticket requires the appropriate signed-in account.

This note summarizes the relevant technical guidance. It does not establish that the firewall has been changed or that authorization now succeeds.

## What Geni support said

- Their security firewall rejects an authorization request when its `redirect_uri` includes `localhost`.
- Use a proper server hostname instead.
- For a local setup, support also suggested choosing a hostname and mapping it in the client computer's hosts file.
- If `localhost` is not the cause, send support the IP address and Incident ID shown on the block page, copied as text, or provide a clearer screenshot. The earlier screenshot was too low-resolution for support to read those details.

The hosts-file suggestion is support's local-computer option, not proof that it will work unchanged across an iPad browser and a remote Devin environment.

## Existing repository implementation

Inspection of `tools/geni_import.py` on main at commit `395b82a09a4210e036cd6aa3897eb6edcbce706d` shows:

- `client_creds()` reads `GENI_APP_ID`, defaulting to 2290.
- `exchange_code()` optionally passes `GENI_REDIRECT_URI` to the token exchange.
- The importer supports an environment-supplied access token and a local token file.
- The authorization URL that failed, its actual redirect value, the registered callback configuration and Devin's current runtime configuration have not been inspected in this handoff.

The support response concerns the authorization request. Changing only the token-exchange environment variable may not change the URL used to start authorization.

## Next work for Devin

1. Read this note and inspect the existing connection setup before changing it. Locate how the authorization URL is generated or assembled and identify its decoded `redirect_uri`. Do not expose credentials, authorization codes, tokens or full credential-bearing URLs in logs or PRs.
2. Check whether that value contains `localhost`. Compare the authorization redirect, application callback configuration and `GENI_REDIRECT_URI` used at exchange time.
3. If it contains `localhost`, prepare the smallest appropriate configuration change using a hostname reachable by the browser completing authorization. Check where the callback listener runs and how that browser can reach it. Use an existing suitable hostname where available; do not assume an iPad can use a hosts-file mapping configured only inside Devin.
4. Have Patrick complete any required Geni sign-in and consent. Retry the normal authorization flow once the callback configuration is consistent.
5. If authorization succeeds, validate the connection with a minimal read-only request for the authorized account/profile. Keep living-person results and credentials out of the public repository.
6. If the firewall block persists, stop repeating the same request. Capture the displayed IP address, Incident ID, timestamp/timezone and a redacted description of the callback configuration. Prepare a reply to ticket 203513; send those diagnostics privately through the support thread, not this public PR.
7. Report the actual result, distinguishing authorization-page access, callback completion, token exchange and successful read-only API access. Propose any implementation changes separately with evidence.

## Completion evidence

- The callback hostname and where it is configured are documented without credentials.
- The result of each attempted stage is recorded, including the stage where it fails.
- A minimal authenticated read succeeds, or the support follow-up has the requested diagnostics.
- Do not mark the connection fixed merely because the PR is merged.

## Alibis

- Actual failing authorization URL and decoded redirect are not yet verified.
- Current registered callback settings and browser/runtime reachability are unknown.
- The blocked page's IP address and Incident ID have not been transcribed.
- No live authorization or API test was performed for this documentation PR.
- This handoff concerns read access. Changes to Geni profiles, relationships, merges or source uploads are outside its scope.
