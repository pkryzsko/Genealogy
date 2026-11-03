#!/usr/bin/env python3
"""Index one blood line from Geni into public (deceased) and private (living) trees.

Scope: anchor profile, all of the anchor's ancestors, and the anchor's siblings.
No spouses (unless they are ancestors) and no descendants of siblings.

Usage:
  geni_import.py auth-url                # start read-only OAuth; requires GENI_REDIRECT_URI
  geni_import.py auth                    # securely prompt for returned code and state
  geni_import.py check                   # authenticated read-only check, no profile output
  (or securely set GENI_ACCESS_TOKEN to use an existing token)
  geni_import.py path                    # show me -> mother -> grandmother for checking
  geni_import.py run --line norway --public-dir DIR --private-dir DIR [--anchor profile-123]

GEDCOM instead of the API (e.g. a Geni or MyHeritage export):
  geni_import.py find --gedcom tree.ged Schultz          # list matching people and their IDs
  geni_import.py path --gedcom tree.ged --me @I1@        # show me -> mother -> grandmother
  geni_import.py run --gedcom tree.ged --line norway --public-dir DIR --private-dir DIR \
      (--anchor @I123@ | --me @I1@)
"""
import argparse
import datetime as dt
import getpass
import json
import os
import re
import secrets
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
from pathlib import Path

API = "https://www.geni.com/api"
AUTHORIZE_URL = "https://www.geni.com/platform/oauth/authorize"
TOKEN_URL = "https://www.geni.com/platform/oauth/request_token"
TOKEN_FILE = Path.home() / ".geni" / "token.json"
STATE_FILE = Path.home() / ".geni" / "oauth-state.json"
STATE_TTL = 600
LIVING_YEARS = 110
FIELDS = ",".join([
    "id", "guid", "name", "display_name", "first_name", "middle_name", "last_name",
    "maiden_name", "suffix", "nicknames", "names", "gender", "is_alive", "birth",
    "baptism", "death", "burial", "occupation", "profile_url", "public", "unions",
])


def client_creds():
    cid = os.environ.get("GENI_APP_ID", "2290")
    secret = os.environ.get("GENI_APP_SECRET")
    if not secret:
        sys.exit("GENI_APP_SECRET is not set")
    return cid, secret


def private_json(path, value):
    """Create files with mode 0600 before writing, then atomically replace."""
    path.parent.mkdir(mode=0o700, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(value, f)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def redirect_uri():
    value = os.environ.get("GENI_REDIRECT_URI", "")
    try:
        url = urllib.parse.urlsplit(value)
        valid = (url.scheme in ("http", "https") and url.hostname
                 and not url.username and not url.password and not url.fragment
                 and not url.query and not any(c.isspace() for c in value))
        url.port  # validate port syntax too
    except ValueError:
        valid = False
    if not valid:
        sys.exit("Set GENI_REDIRECT_URI to an absolute HTTP(S) callback without query or fragment")
    host = url.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        sys.exit("Use a proper callback hostname matching the Geni app settings; localhost may be blocked")
    return value  # preserve the exact spelling for both OAuth steps


def authorization_url():
    redirect = redirect_uri()
    pending = {"state": secrets.token_urlsafe(32), "redirect_uri": redirect,
               "client_id": os.environ.get("GENI_APP_ID", "2290"),
               "created_at": time.time()}
    private_json(STATE_FILE, pending)
    return AUTHORIZE_URL + "?" + urllib.parse.urlencode({
        "client_id": pending["client_id"], "redirect_uri": redirect,
        "response_type": "code", "scope": "read_profile", "state": pending["state"]})


def save_token(tok):
    tok["obtained_at"] = int(time.time())
    private_json(TOKEN_FILE, tok)


def token_request(params):
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=data), timeout=30) as r:
            tok = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"Token request failed: HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError, ValueError):
        sys.exit("Token request failed: transport or invalid JSON response")
    if not isinstance(tok, dict) or not tok.get("access_token"):
        sys.exit("Token request failed: no access token returned")
    tok["redirect_uri"] = params["redirect_uri"]
    save_token(tok)
    return tok


def exchange_code(code, state):
    redirect = redirect_uri()
    try:
        pending = json.loads(STATE_FILE.read_text())
        age = time.time() - pending["created_at"]
        valid = (0 <= age < STATE_TTL and isinstance(state, str) and bool(state)
                 and secrets.compare_digest(state.encode(), pending["state"].encode())
                 and redirect == pending["redirect_uri"]
                 and os.environ.get("GENI_APP_ID", "2290") == pending["client_id"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        valid = False
    if not valid or not code:
        sys.exit("OAuth state missing, invalid, expired, or configuration changed; run auth-url again")
    cid, secret = client_creds()
    # Consume this single-use state before sending a code, including on exchange failure.
    try:
        STATE_FILE.unlink()
    except FileNotFoundError:
        sys.exit("OAuth state already consumed; run auth-url again")
    params = {"client_id": cid, "client_secret": secret, "code": code,
              "grant_type": "authorization_code", "redirect_uri": pending["redirect_uri"]}
    token_request(params)
    print("Token stored at", TOKEN_FILE)


def hidden_input(prompt):
    # getpass otherwise falls back to echoing input when terminal control fails.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass(prompt)
    except (getpass.GetPassWarning, EOFError):
        sys.exit("Hidden input unavailable; securely set GENI_AUTH_CODE and GENI_AUTH_STATE")


def access_token():
    if os.environ.get("GENI_ACCESS_TOKEN"):
        return os.environ["GENI_ACCESS_TOKEN"]
    if os.environ.get("GENI_REFRESH_TOKEN") and not TOKEN_FILE.exists():
        cid, secret = client_creds()
        token_request({"client_id": cid, "client_secret": secret,
                       "grant_type": "refresh_token",
                       "refresh_token": os.environ["GENI_REFRESH_TOKEN"],
                       "redirect_uri": redirect_uri()})
    if not TOKEN_FILE.exists():
        sys.exit("No token. Run auth-url, authorize in your browser, then run auth")
    tok = json.loads(TOKEN_FILE.read_text())
    if time.time() > tok["obtained_at"] + int(tok.get("expires_in", 0)) - 120:
        redirect = redirect_uri()
        if tok.get("redirect_uri", redirect) != redirect:
            sys.exit("GENI_REDIRECT_URI differs from the stored token callback")
        cid, secret = client_creds()
        tok = token_request({"client_id": cid, "client_secret": secret,
                             "grant_type": "refresh_token",
                             "refresh_token": tok["refresh_token"], "redirect_uri": redirect})
    return tok["access_token"]


class Geni:
    def __init__(self):
        self.token = access_token()
        self.cache = {}

    def get(self, path, **params):
        url = f"{API}/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        for attempt in range(5):
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    body = json.load(r)
                    remaining = int(r.headers.get("X-API-Rate-Remaining", "1"))
                    window = int(r.headers.get("X-API-Rate-Window", "10"))
                if remaining <= 1:
                    time.sleep(window)
                return body
            except urllib.error.HTTPError as e:
                if e.code in (429, 503):
                    time.sleep(10 * (attempt + 1))
                    continue
                raise SystemExit(f"Geni GET failed: HTTP {e.code}")
            except (urllib.error.URLError, TimeoutError, ValueError):
                raise SystemExit("Geni GET failed: transport or invalid JSON response")
        raise SystemExit(f"GET {path} kept failing (rate limit)")

    source = "geni.com API"

    def me(self):
        return self.get("profile", fields=FIELDS)

    def profile(self, pid):
        if pid not in self.cache:
            self.cache[pid] = self.get(pid, fields=FIELDS)
        return self.cache[pid]

    def family(self, pid):
        """Return (parents, siblings) as lists of (profile_id, note)."""
        nodes = self.get(f"{pid}/immediate-family", fields=FIELDS).get("nodes", {})
        for nid, node in nodes.items():
            if nid.startswith("profile-"):
                self.cache.setdefault(nid, node)
        me = nodes.get(pid, {})
        birth_unions = [u for u, e in me.get("edges", {}).items() if e.get("rel") == "child"]
        parents, siblings = [], []
        parent_ids = set()
        for u in birth_unions:
            for p, e in nodes.get(u, {}).get("edges", {}).items():
                if e.get("rel") == "partner":
                    parents.append(p)
                    parent_ids.add(p)
        for u in birth_unions:
            for p, e in nodes.get(u, {}).get("edges", {}).items():
                if e.get("rel") == "child" and p != pid:
                    siblings.append((p, "sibling"))
        # Half-siblings: children of a parent's other unions (only if they appear in the response).
        for uid, node in nodes.items():
            if not uid.startswith("union-") or uid in birth_unions:
                continue
            edges = node.get("edges", {})
            if any(p in parent_ids and e.get("rel") == "partner" for p, e in edges.items()):
                for p, e in edges.items():
                    if e.get("rel") == "child" and p != pid:
                        siblings.append((p, "half-sibling"))
        return parents, siblings


EVENTS = {"BIRT": "birth", "CHR": "baptism", "BAPM": "baptism", "DEAT": "death", "BURI": "burial"}
MONTHS = {m: i for i, m in enumerate(
    "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}


def gedcom_date(raw):
    date = {"raw": raw}
    words = raw.upper().split()
    years = [w for w in words if re.fullmatch(r"\d{3,4}(/\d{1,2})?", w)]
    if years:
        date["year"] = int(years[0].split("/")[0])
        i = words.index(years[0])
        if i >= 1 and words[i - 1] in MONTHS:
            date["month"] = MONTHS[words[i - 1]]
            if i >= 2 and words[i - 2].isdigit():
                date["day"] = int(words[i - 2])
    return date


def gid(xref):
    return "gedcom-" + xref.strip("@")


class Gedcom:
    """Reads a GEDCOM file and offers the same profile()/family() interface as Geni."""

    def __init__(self, path):
        self.source = f"GEDCOM file {Path(path).name}"
        self.cache, self.fams = {}, {}
        records, cur = [], None
        for raw in Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines():
            m = re.match(r"\s*(\d+)\s+(@[^@]+@\s+)?(\S+)\s?(.*)$", raw)
            if not m:
                continue
            level, xref, tag, val = int(m[1]), (m[2] or "").strip(), m[3], m[4]
            if tag in ("CONC", "CONT") and cur and cur["stack"]:
                node = cur["stack"][-1]
                node["val"] += ("\n" if tag == "CONT" else "") + val
                continue
            node = {"tag": tag, "val": val, "kids": []}
            if level == 0:
                cur = dict(node, xref=xref)
                cur["stack"] = [cur]
                records.append(cur)
                continue
            if not cur:
                continue
            stack = cur["stack"]
            del stack[level:]
            stack[level - 1]["kids"].append(node)
            stack.append(node)
        for r in records:
            if r["tag"] == "INDI":
                self.cache[gid(r["xref"])] = self._person(r)
            elif r["tag"] == "FAM":
                f = {"parents": [], "children": []}
                for k in r["kids"]:
                    if k["tag"] in ("HUSB", "WIFE"):
                        f["parents"].append(gid(k["val"]))
                    elif k["tag"] == "CHIL":
                        f["children"].append(gid(k["val"]))
                self.fams[r["xref"]] = f

    @staticmethod
    def _person(r):
        p = {"id": gid(r["xref"]), "gedcom_xref": r["xref"], "famc": [], "fams": []}
        for k in r["kids"]:
            sub = {c["tag"]: c["val"] for c in k["kids"]}
            if k["tag"] == "NAME" and "first_name" not in p:
                given = sub.get("GIVN") or k["val"].split("/")[0].strip()
                surname = sub.get("SURN") or (k["val"].split("/") + ["", ""])[1].strip()
                p.update(first_name=given, last_name=surname,
                         name=" ".join(x for x in [given, surname] if x))
                if sub.get("_MARNM"):
                    p["married_name"] = sub["_MARNM"]
            elif k["tag"] == "SEX":
                p["gender"] = {"M": "male", "F": "female"}.get(k["val"].strip().upper(), "unknown")
            elif k["tag"] in EVENTS and EVENTS[k["tag"]] not in p:
                ev = {}
                if sub.get("DATE"):
                    ev["date"] = gedcom_date(sub["DATE"])
                if sub.get("PLAC"):
                    ev["location"] = {"place_name": sub["PLAC"]}
                p[EVENTS[k["tag"]]] = ev or {"recorded": True}
            elif k["tag"] == "OCCU":
                p["occupation"] = k["val"]
            elif k["tag"] in ("_UID", "UID"):
                p["guid"] = k["val"]
            elif k["tag"] in ("WWW", "_URL", "URL") and "profile_url" not in p:
                p["profile_url"] = k["val"]
            elif k["tag"] == "FAMC":
                pedi = (sub.get("PEDI") or "birth").lower()
                if pedi in ("birth", "natural"):
                    p["famc"].append(k["val"])
            elif k["tag"] == "FAMS":
                p["fams"].append(k["val"])
        return p

    def me(self):
        sys.exit("With --gedcom, pass --me @I..@ (your own record; see the find command)")

    def profile(self, pid):
        if pid not in self.cache:
            sys.exit(f"{pid} is not in the GEDCOM file")
        return self.cache[pid]

    def family(self, pid):
        p = self.profile(pid)
        parents, siblings, seen = [], [], {pid}
        for f in p["famc"]:
            fam = self.fams.get(f, {"parents": [], "children": []})
            parents += [x for x in fam["parents"] if x not in parents]
            for c in fam["children"]:
                if c not in seen:
                    seen.add(c)
                    siblings.append((c, "sibling"))
        for par in parents:
            for f in self.profile(par)["fams"]:
                if f in p["famc"]:
                    continue
                for c in self.fams.get(f, {"children": []})["children"]:
                    if c not in seen:
                        seen.add(c)
                        siblings.append((c, "half-sibling"))
        return parents, siblings

    def find(self, text):
        t = text.lower()
        return [p for p in self.cache.values()
                if t in " ".join(str(p.get(k, "")) for k in ("name", "married_name")).lower()]


def open_source(args):
    if getattr(args, "gedcom", None):
        return Gedcom(args.gedcom)
    return Geni()


def ref(g, value):
    """Accept '@I12@', 'I12' or 'gedcom-I12' for GEDCOM sources; pass Geni ids through."""
    if value and isinstance(g, Gedcom) and not value.startswith("gedcom-"):
        return gid(value)
    return value


def year(event):
    date = (event or {}).get("date") or {}
    return date.get("year")


def is_living(p):
    if p.get("is_alive") is True:
        return True
    if p.get("death") or p.get("burial"):
        return False
    by = year(p.get("birth")) or year(p.get("baptism"))
    if by is None:
        return True
    return dt.date.today().year - int(by) < LIVING_YEARS


def label(p):
    return p.get("display_name") or p.get("name") or " ".join(
        x for x in [p.get("first_name"), p.get("last_name")] if x) or p.get("id")


def mother_of(g, pid):
    parents, _ = g.family(pid)
    moms = [p for p in parents if g.profile(p).get("gender") == "female"]
    if len(moms) != 1:
        sys.exit(f"Could not identify exactly one mother for {pid}: {[label(g.profile(p)) for p in parents]}")
    return moms[0]


def default_path(g, me_id=None):
    if me_id:
        me = g.profile(me_id)
    else:
        me = g.me()
        g.cache[me["id"]] = me
    mom = mother_of(g, me["id"])
    gma = mother_of(g, mom)
    return [me["id"], mom, gma]


def describe(p):
    b, d = year(p.get("birth")), year(p.get("death"))
    names = [p.get("maiden_name"), p.get("last_name")]
    return f"{label(p)} (born {b or '?'}, died {d or '-'}; surnames: {', '.join(n for n in names if n) or '?'})"


def collect(g, anchor):
    people = {anchor: {"relation": "anchor", "generation": 0}}
    parents_of = {}
    queue = [anchor]
    while queue:
        pid = queue.pop(0)
        parents, siblings = g.family(pid)
        parents_of[pid] = parents
        gen = people[pid]["generation"]
        for par in parents:
            if par not in people:
                people[par] = {"relation": "ancestor", "generation": gen + 1}
                queue.append(par)
        if pid == anchor:
            for sib, note in siblings:
                people.setdefault(sib, {"relation": note, "generation": 0})
    return people, parents_of


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def record(g, pid, meta):
    p = g.profile(pid)
    keys = FIELDS.split(",") + ["gedcom_xref", "married_name"]
    keep = {k: p.get(k) for k in keys if p.get(k) not in (None, "", [], {})}
    keep.pop("unions", None)
    keep.update(meta)
    return keep


def mermaid(people, parents_of, g, include):
    lines = ["flowchart BT"]
    for pid in people:
        if pid in include:
            p = g.profile(pid)
            b, d = year(p.get("birth")), year(p.get("death"))
            text = f"{label(p)}<br/>{b or '?'}–{d or ''}".replace('"', "'")
            lines.append(f'  {pid.replace("-", "_")}["{text}"]')
    for child, parents in parents_of.items():
        for par in parents:
            if child in include and par in include:
                lines.append(f"  {child.replace('-', '_')} --> {par.replace('-', '_')}")
    return "\n".join(lines) + "\n"


def write_tree(root, line, entries, diagram, today, source):
    base = Path(root) / line
    (base / "profiles").mkdir(parents=True, exist_ok=True)
    index = []
    for e in sorted(entries, key=lambda e: (e["generation"], e.get("display_name") or e.get("name") or "")):
        fname = f"profiles/{slug(e.get('display_name') or e.get('name') or e['id'])}-{e['id']}.json"
        (base / fname).write_text(json.dumps(e, indent=2, ensure_ascii=False) + "\n")
        index.append({"id": e["id"], "name": e.get("display_name") or e.get("name"),
                      "relation": e["relation"], "generation": e["generation"],
                      "birth_year": year(e.get("birth")), "death_year": year(e.get("death")),
                      "file": fname, "geni_url": e.get("profile_url")})
    (base / "index.json").write_text(json.dumps(
        {"line": line, "imported": today, "source": source, "count": len(index),
         "profiles": index}, indent=2, ensure_ascii=False) + "\n")
    (base / "tree.mmd").write_text(diagram)
    return len(index)


def run(args):
    g = open_source(args)
    anchor = ref(g, args.anchor) or default_path(g, ref(g, args.me))[-1]
    print("Anchor:", describe(g.profile(anchor)))
    people, parents_of = collect(g, anchor)
    today = dt.date.today().isoformat()
    public, private = [], []
    for pid, meta in people.items():
        rec = record(g, pid, meta)
        rec["living"] = is_living(g.profile(pid))
        (private if rec["living"] else public).append(rec)
    pub_ids = {r["id"] for r in public}
    n_pub = write_tree(args.public_dir, args.line, public,
                       mermaid(people, parents_of, g, pub_ids), today, g.source)
    n_priv = write_tree(args.private_dir, args.line, public + private,
                        mermaid(people, parents_of, g, set(people)), today, g.source)
    print(f"Public (deceased): {n_pub}  Private (all incl. living): {n_priv}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth-url")
    a = sub.add_parser("auth")
    a.add_argument("--code", default=os.environ.get("GENI_AUTH_CODE"),
                   help="prefer the hidden prompt or GENI_AUTH_CODE to avoid shell history")
    a.add_argument("--state", default=os.environ.get("GENI_AUTH_STATE"),
                   help="returned callback state; prefer the hidden prompt")
    sub.add_parser("check")
    pa = sub.add_parser("path")
    sub.add_parser("whoami")
    f = sub.add_parser("find")
    f.add_argument("--gedcom", required=True)
    f.add_argument("text")
    r = sub.add_parser("run")
    for sp in (pa, r):
        sp.add_argument("--gedcom", help="read this GEDCOM file instead of the Geni API")
        sp.add_argument("--me", help="with --gedcom: your own record id, e.g. @I1@")
    r.add_argument("--line", required=True)
    r.add_argument("--public-dir", required=True)
    r.add_argument("--private-dir", required=True)
    r.add_argument("--anchor")
    args = ap.parse_args()
    if args.cmd == "auth-url":
        print(authorization_url())
    elif args.cmd == "auth":
        if (not args.code or not args.state) and not sys.stdin.isatty():
            sys.exit("Use an interactive terminal or securely set GENI_AUTH_CODE and GENI_AUTH_STATE")
        code = args.code or hidden_input("Code from Geni callback (hidden): ")
        state = args.state or hidden_input("State from Geni callback (hidden): ")
        exchange_code(code, state)
    elif args.cmd == "check":
        me = Geni().get("profile", fields="id")
        if not isinstance(me, dict) or not me.get("id"):
            sys.exit("Read-only check failed: no profile id returned")
        print("Authenticated read-only Geni request succeeded (profile id received; value withheld)")
    elif args.cmd == "whoami":
        me = Geni().get("profile", fields="id,display_name,name")
        print("Signed in as:", me.get("display_name") or me.get("name"), me.get("id"))
    elif args.cmd == "find":
        for p in Gedcom(args.gedcom).find(args.text):
            print(p["gedcom_xref"], describe(p))
    elif args.cmd == "path":
        g = open_source(args)
        for role, pid in zip(["You", "Mother", "Grandmother"], default_path(g, ref(g, args.me))):
            print(f"{role}: {describe(g.profile(pid))}")
    else:
        run(args)


if __name__ == "__main__":
    main()

