"""Read Meshy cookies from Chrome via immutable SQLite + DPAPI."""
from __future__ import annotations

import base64
import json
import os
import sqlite3
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from win32crypt import CryptUnprotectData

LOCAL = Path(os.environ["LOCALAPPDATA"])
SRC = LOCAL / "Google/Chrome/User Data/Default/Network/Cookies"
OUT = Path(os.environ["TEMP"]) / "meshy_cookies.json"


def decrypt(val: bytes, key: bytes) -> str:
    if not val:
        return ""
    if val.startswith((b"v10", b"v20")):
        return AESGCM(key).decrypt(val[3:15], val[15:], None).decode("utf-8", errors="replace")
    return CryptUnprotectData(val, None, None, None, 0)[1].decode("utf-8", errors="replace")


def main() -> None:
    uri = "file:" + str(SRC).replace("\\", "/") + "?mode=ro&immutable=1"
    con = sqlite3.connect(uri, uri=True)
    rows = con.execute(
        "SELECT host_key, name, encrypted_value FROM cookies WHERE host_key LIKE '%meshy%'"
    ).fetchall()
    print("rows", len(rows))
    ls = json.loads((LOCAL / "Google/Chrome/User Data/Local State").read_text(encoding="utf-8"))
    key = CryptUnprotectData(base64.b64decode(ls["os_crypt"]["encrypted_key"])[5:], None, None, None, 0)[1]
    cookies: dict[str, str] = {}
    for host, name, enc in rows:
        try:
            val = decrypt(enc, key)
        except Exception as e:
            val = f"err:{e}"
        cookies[name] = val
        print(name, val[:60])
    OUT.write_text(json.dumps(cookies), encoding="utf-8")
    auth = [k for k in cookies if any(x in k.lower() for x in ("token", "session", "auth", "jwt", "access"))]
    print("saved", OUT)
    print("auth-like", auth)


if __name__ == "__main__":
    main()
