import argparse
from email.mime import base
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urljoin, urlunparse, urlencode, urlsplit, urlunsplit, parse_qsl
import json
from datetime import datetime
import requests
import shutil
import urllib3


# Programm welches eine einzelne ABAP Quelle von einem ADT Server holt,
# mit abap-cleaner bereinigt und wahlweise lokal speichert (test)
# oder zurück ins SAP Objekt schreibt (writeback).
CLEANER_DEFAULT = r"C:\Tools\abap-cleaner-standalone\abapcleaner\abap-cleanerc.exe"
SAP_CLIENT_DEFAULT = "001"


@dataclass(frozen=True)
class SourceItem:
    url: str          # absolute URL to ADT source/main (or other text endpoint)
    label: str        # for output naming / logging


def safe_filename(s: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", s).strip(" .") or "unnamed"


def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess:
    # bytes in stdout/stderr
    return subprocess.run(cmd, capture_output=True, check=False)


def run_cleaner(cleaner_exe: str, profile: Path, release: str, source: str) -> str:
    if not Path(cleaner_exe).exists():
        raise FileNotFoundError(f"Cleaner nicht gefunden: {cleaner_exe}")
    if not profile.exists():
        raise FileNotFoundError(f"Profil nicht gefunden: {profile}")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        src = td / "in.abap"
        src.write_text(source, encoding="utf-8")

        cmd = [
            cleaner_exe,
            "--sourcefile", str(src),
            "--profile", str(profile),
            "--release", str(release),
        ]
        res = run_cmd(cmd)

        # stderr/stdout: bytes -> str
        stderr_b = res.stderr or b""
        stdout_b = res.stdout or b""

        def decode_best(b: bytes) -> str:
            try:
                return b.decode("utf-8")
            except UnicodeDecodeError:
                return b.decode("cp1252", errors="replace")

        stderr_s = decode_best(stderr_b)
        stdout_s = decode_best(stdout_b)

        if res.returncode != 0:
            raise RuntimeError(f"Cleaner failed rc={res.returncode}\n{stderr_s}\n{stdout_s}")

        out = stdout_s
        if not out.strip():
            raise RuntimeError(f"Cleaner returned empty output.\nSTDERR:\n{stderr_s[:800]}")

        return out



def headers(client: str, accept: str) -> dict:
    return {
        "sap-client": client,
        "Accept": accept,
        "Accept-Charset": "utf-8",
        "User-Agent": "adt-client",
    }


def adt_get_text_and_etag(session: requests.Session, url: str, client: str) -> tuple[str, str | None]:
    r = session.get(url, headers=headers(client, "text/plain, */*"))
    r.raise_for_status()

    raw = r.content  # bytes

    # ADT Source ist i.d.R. UTF-8
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8-sig", errors="replace")

    return text, r.headers.get("ETag")



def fetch_csrf_token(session: requests.Session, any_adt_url: str, client: str) -> str:
    h = headers(client, "text/plain, */*")
    h["X-CSRF-Token"] = "Fetch"
    r = session.get(any_adt_url, headers=h)
    r.encoding = "utf-8"
    r.raise_for_status()
    token = r.headers.get("X-CSRF-Token") or r.headers.get("x-csrf-token")
    if not token:
        raise RuntimeError("Konnte keinen X-CSRF-Token erhalten (Header fehlt).")
    return token


def adt_put_text(session: requests.Session, url: str, client: str, text: str, csrf_token: str, etag: str | None):
    h = headers(client, "text/plain, */*")
    h["Content-Type"] = "text/plain; charset=utf-8"
    h["X-CSRF-Token"] = csrf_token
    h["If-Match"] = etag if etag else "*"

    r = session.put(url, headers=h, data=text.encode("utf-8"))

    if r.status_code >= 400:
        raise RuntimeError(
            f"PUT failed {r.status_code} {r.reason}\n"
            f"URL: {url}\n"
            f"Response headers: {dict(r.headers)}\n"
            f"Response body:\n{r.text[:4000]}"
        )
    return r


def is_absolute_url(s: str) -> bool:
    try:
        p = urlparse(s)
        return bool(p.scheme and p.netloc)
    except Exception:
        return False
    
def add_query_param(url: str, key: str, value: str) -> str:
    s = urlsplit(url)
    q = dict(parse_qsl(s.query, keep_blank_values=True))
    q[key] = value
    return urlunsplit((s.scheme, s.netloc, s.path, urlencode(q, doseq=True), s.fragment))


def label_from_url(u: str) -> str:
    """
    Extract a nice label from common ADT paths.
    Examples:
      /programs/programs/Z_TEST1/source/main       -> Z_TEST1
      /oo/classes/ZCL_FOO/source/main              -> ZCL_FOO
      /oo/interfaces/ZIF_BAR/source/main           -> ZIF_BAR
      /ddic/tables/ZTAB/source/main                -> ZTAB
    Fallback: last segments joined.
    """
    p = urlparse(u)
    parts = [x for x in p.path.strip("/").split("/") if x]

    # Helper: find token right after a marker path
    def after(*marker):
        for i in range(len(parts) - len(marker)):
            if parts[i:i+len(marker)] == list(marker):
                if i + len(marker) < len(parts):
                    return parts[i + len(marker)]
        return None

    # Common ADT patterns
    name = (
        after("programs", "programs") or
        after("oo", "classes") or
        after("oo", "interfaces") or
        after("ddic", "tables") or
        after("ddic", "structures") or
        after("ddic", "dataelements") or
        after("ddic", "domains")
    )

    if name:
        return safe_filename(name)

    # Fallback: keep something stable
    tail = parts[-4:] if len(parts) >= 4 else parts
    return safe_filename("_".join(tail))

def adt_activate(session: requests.Session, base: str, obj_url: str, client: str, csrf_token: str, corrnr: str):
    """
    Aktiviert ein ADT-Objekt nach Writeback.
    obj_url = source/main URL (mit oder ohne Query)
    """
    # aus /source/main -> /activation machen
    activation_url = obj_url.split("/source/")[0] + "/activation"

    # corrNr anhängen
    activation_url = add_query_param(activation_url, "corrNr", corrnr)

    h = headers(client, "application/vnd.sap.adt.errors+xml")
    h["X-CSRF-Token"] = csrf_token

    r = session.post(activation_url, headers=h)
    if r.status_code >= 400:
        raise RuntimeError(
            f"ACTIVATION failed {r.status_code} {r.reason}\n"
            f"URL: {activation_url}\n"
            f"Response body:\n{r.text[:4000]}"
        )

def read_urls_file(path: Path) -> list[str]:
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        urls.append(s)
    return urls


def build_source_items(base: str, url_args: list[str], urls_file: str | None) -> list[SourceItem]:
    raw: list[str] = []
    raw.extend(url_args or [])

    if urls_file:
        p = Path(urls_file)
        if not p.exists():
            raise SystemExit(f"ERROR: urls-file nicht gefunden: {p}")
        raw.extend(read_urls_file(p))

    # Dedup while preserving order
    seen = set()
    unique: list[str] = []
    for u in raw:
        if u not in seen:
            seen.add(u)
            unique.append(u)

    items: list[SourceItem] = []
    for u in unique:
        if is_absolute_url(u):
            full = u
        else:
            full = urljoin(base.rstrip("/") + "/", u.lstrip("/"))
        items.append(SourceItem(url=full, label=label_from_url(full)))
    return items

def read_urls_file(path: Path) -> list[str]:
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        urls.append(s)
    return urls



def adt_activate_via_service(session, obj_url: str, client: str, csrf_token: str, corrnr: str):
    """
    Aktiviert ein ADT-Objekt per zentralem /sap/bc/adt/activation Service.
    obj_url muss eine ABSOLUTE URL sein, z.B.:
      https://host:port/sap/bc/adt/programs/programs/Z_TEST1/source/main?version=inactive
    """

    # 1) Query weg + ggf. /source/main entfernen -> Objekt-Root
    u = obj_url.split("?", 1)[0]
    if "/source/" in u:
        u = u.split("/source/", 1)[0]

    p = urlparse(u)
    if not (p.scheme and p.netloc):
        raise ValueError(f"obj_url muss absolut sein: {obj_url}")

    # 2) rel_uri für XML: nur der Pfad des Objekt-Roots, z.B. /sap/bc/adt/programs/programs/Z_TEST1
    rel_uri = p.path

    # 3) Activation-Service-URL auf demselben Host: /sap/bc/adt/activation
    #    -> Wir nehmen den Prefix bis /sap/bc/adt aus dem Pfad.
    marker = "/sap/bc/adt"
    idx = rel_uri.find(marker)
    if idx < 0:
        raise ValueError(f"URL enthält nicht {marker}: {obj_url}")

    adt_root_path = rel_uri[: idx + len(marker)]          # /sap/bc/adt
    act_path = adt_root_path + "/activation"              # /sap/bc/adt/activation

    act_url = urlunparse((p.scheme, p.netloc, act_path, "", "", ""))
    act_url = add_query_param(act_url, "method", "activate")
    act_url = add_query_param(act_url, "corrNr", corrnr)

    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<adtcore:objectReferences xmlns:adtcore="http://www.sap.com/adt/core">
  <adtcore:objectReference adtcore:uri="{rel_uri}"/>
</adtcore:objectReferences>
"""

    h = headers(client, "application/vnd.sap.adt.errors+xml, application/xml, */*")
    h["Content-Type"] = "application/vnd.sap.adt.core.objectreferences+xml; charset=utf-8"
    h["X-CSRF-Token"] = csrf_token

    r = session.post(act_url, headers=h, data=body.encode("utf-8"))
    if r.status_code >= 400:
        raise RuntimeError(
            f"ACTIVATION failed {r.status_code} {r.reason}\n"
            f"act_url: {act_url}\n"
            f"rel_uri: {rel_uri}\n"
            f"Response body:\n{r.text[:4000]}"
        )
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="Base ADT URL, e.g. https://host:port")
    ap.add_argument("--client", default=SAP_CLIENT_DEFAULT)
    ap.add_argument("--release", default="757")
    ap.add_argument("--profile", default=str(Path(__file__).resolve().parent / "profile+REMOVE.cfj"))
    ap.add_argument("--cleaner", default=CLEANER_DEFAULT)
    ap.add_argument("--outdir", default=str(Path(__file__).resolve().parent / "outputs"))
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument(
        "--mode",
        choices=["test", "writeback", "writeback_noact"],
        default="test",
        help=(
            "test = lokal speichern, "
            "writeback = cleaned Source per ADT zurückschreiben + aktivieren, "
            "writeback_noact = cleaned Source zurückschreiben, aber NICHT aktivieren"
        )
    )

    # URLs input
    ap.add_argument(
        "--url",
        action="append",
        default=[],
        help="ADT source URL or relative ADT path. Can be used multiple times."
    )
    ap.add_argument(
        "--urls-file",
        default=None,
        help="Text file with one URL/path per line (lines starting with # are ignored)."
    )

    ap.add_argument(
    "--corrnr",
    default=None,
    help="Transport request number (corrNr), e.g. DEVK900123. Required for writeback on many systems."
    )

    args = ap.parse_args()

    if args.insecure:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    user = os.getenv("SAP_USER")
    pw = os.getenv("SAP_PASS")
    if not user or not pw:
        raise SystemExit("ERROR: Setze SAP_USER und SAP_PASS als Environment Variables.")

    base = args.base.rstrip("/")

    outdir = Path(args.outdir)

    if outdir.exists():
        print(f"[info] cleaning output dir: {outdir}")
        shutil.rmtree(outdir)

    outdir.mkdir(parents=True, exist_ok=True)


    items = build_source_items(base, args.url, args.urls_file)
    if not items:
        raise SystemExit(
            "ERROR: Keine URLs angegeben.\n"
            "Nutze z.B.:\n"
            "  --url /programs/programs/ZPROG/source/main?version=inactive --url /oo/classes/ZCL_FOO/source/main\n"
            "oder:\n"
            "  --urls-file urls.txt"
        )

    s = requests.Session()
    s.auth = (user, pw)
    s.verify = (not args.insecure)

    csrf_token = None
    if args.mode in ("writeback", "writeback_noact"):
        csrf_token = fetch_csrf_token(s, items[0].url, args.client)

    ok = 0
    fail = 0

    print(f"[info] mode: {args.mode}")
    print(f"[info] items: {len(items)}")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    fail_log = outdir / f"failures_{run_id}.txt"
    fail_json = outdir / f"failures_{run_id}.jsonl" 
    retry_file = outdir / f"retry_urls_{run_id}.txt"

    failures = []
    retry_urls = []

    for it in items:
        try:
            source, etag = adt_get_text_and_etag(s, it.url, args.client)
            cleaned = run_cleaner(args.cleaner, Path(args.profile), args.release, source)

            if args.mode == "test":
                out_path = outdir / f"{safe_filename(it.label)}.abap"
                out_path.write_text(cleaned, encoding="utf-8")
                print(f"[ok] TEST  {it.url} -> {out_path}")

            else:
                # writeback / writeback_noact
                assert csrf_token is not None

                if not args.corrnr:
                    raise SystemExit("ERROR: --corrnr ist im writeback Modus erforderlich.")

                put_url = add_query_param(it.url, "corrNr", args.corrnr)

                adt_put_text(s, put_url, args.client, cleaned, csrf_token, etag)
                print(f"[ok] WRITE {put_url} -> updated on server")

                if args.mode == "writeback":
                    adt_activate_via_service(s, it.url, args.client, csrf_token, args.corrnr)
                    print(f"[ok] ACTIVATE {it.label}")

            ok += 1
        except Exception as e:
            msg = str(e)

            # ADT lock corrNr rausziehen, falls vorhanden
            m_lock = re.search(r"locked in request\s+([A-Z0-9]{10})", msg)
            lock_corrnr = m_lock.group(1) if m_lock else None

            entry = {
                "label": it.label,
                "url": it.url,
                "error": msg[:4000],
                "lock_corrnr": lock_corrnr,
            }
            failures.append(entry)
            retry_urls.append(it.url)

            print(f"[fail] {it.url} ")

            # txt log (human readable)
            with fail_log.open("a", encoding="utf-8") as f:
                f.write(f"---\nLABEL: {it.label}\nURL: {it.url}\n")
                if lock_corrnr:
                    f.write(f"LOCKED_IN: {lock_corrnr}\n")
                f.write(f"ERROR:\n{msg}\n")

            # jsonl log (maschinenlesbar)
            with fail_json.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

            fail += 1
            continue

    if retry_urls:
        retry_file.write_text("\n".join(retry_urls) + "\n", encoding="utf-8")

    print(f"[info] failure log: {fail_log}")
    print(f"[info] failure jsonl: {fail_json}")
    print(f"[info] retry urls: {retry_file}")

    print(f"\nDONE: ok={ok} fail={fail} outdir={outdir}")


if __name__ == "__main__":
    main()
