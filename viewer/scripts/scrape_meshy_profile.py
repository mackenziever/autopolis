"""Scrape public Meshy profile model pages and download GLB when CDN URL is public."""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CivitasMeshy/1.0"}
CDN = "https://cdn.meshy.ai/"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", errors="replace")


def profile_model_links(profile_url: str, max_pages: int = 3) -> list[str]:
    html = fetch(profile_url)
    links = sorted(
        set(
            re.findall(
                r"https://www\.meshy\.ai/(?:it/)?3d-models/[a-z0-9\-]+",
                html,
                flags=re.I,
            )
        )
    )
    # Also relative
    for rel in re.findall(r'href="(/[^"]*3d-models/[^"]+)"', html):
        links.append(urllib.parse.urljoin("https://www.meshy.ai", rel))
    # dedupe
    out, seen = [], set()
    for u in links:
        u = u.split("?")[0]
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def extract_glb_candidates(html: str) -> list[str]:
    cands: list[str] = []
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, flags=re.S)
    blob = m.group(1) if m else html
    cands += re.findall(r"https?://[^\"\\]+\.glb[^\"\\]*", blob, flags=re.I)
    for path in re.findall(r"uploads/[^\"\\]+\.glb", blob, flags=re.I):
        cands.append(CDN + path.replace("\\u002F", "/"))
    # truncated gl paths in modelId
    for path in re.findall(r"uploads/[a-f0-9]{20,}[^\"\\]*?\.gl[^\"]*", blob, flags=re.I):
        path = path.replace("\\u002F", "/")
        if path.endswith(".gl"):
            path += "b"
        if ".glb" in path.lower():
            cands.append(CDN + path if not path.startswith("http") else path)
    # unique preserve
    out, seen = [], set()
    for c in cands:
        c = c.replace("\\u002F", "/").split("?")[0]
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def slug_from_url(url: str) -> str:
    name = url.rstrip("/").split("/")[-1]
    name = re.sub(r"-[0-9a-f]{8}-[0-9a-f]{4}-.*$", "", name, flags=re.I)
    name = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_").lower()
    return name[:64] or "character"


def download(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        if len(data) < 1000 or not (data[:4] in (b"glTF", b"glT") or data[:4] == b"glTF" or True):
            # GLB magic is 'glTF'
            if data[:4] != b"glTF":
                print(f"[skip] not glb magic {url} size={len(data)} head={data[:8]!r}")
                return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        print(f"[ok] {dest.name} ({len(data)} bytes) <- {url}")
        return True
    except Exception as exc:
        print(f"[fail] {url}: {exc}")
        return False


def main() -> int:
    profile = sys.argv[1] if len(sys.argv) > 1 else "https://www.meshy.ai/it/@s1747943328efd79"
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("viewer/assets/models/citizens/meshy")
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    links = profile_model_links(profile)[:limit]
    print(f"[info] models={len(links)} out={out_dir}")
    meta = []
    ok = 0
    for link in links:
        slug = slug_from_url(link)
        try:
            html = fetch(link)
        except Exception as exc:
            print(f"[fail] page {link}: {exc}")
            continue
        glbs = extract_glb_candidates(html)
        print(f"[info] {slug}: candidates={len(glbs)}")
        saved = False
        for g in glbs:
            dest = out_dir / f"{slug}.glb"
            if download(g, dest):
                meta.append({"slug": slug, "source": link, "cdn": g, "file": str(dest)})
                ok += 1
                saved = True
                break
        if not saved:
            # dump debug hints
            m = re.search(r"modelId\\\":\\\"([^\\\"]+)\\\"", html)
            print(f"[miss] {slug} modelId={m.group(1) if m else None}")
    (out_dir / "import_manifest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"[done] downloaded={ok}/{len(links)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
