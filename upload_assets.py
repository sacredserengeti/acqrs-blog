#!/usr/bin/env python3
"""Upload the static site's bytes to a Workers assets upload session.

Usage: python3 upload_assets.py <upload_jwt_file>
Reads site/ + manifest, POSTs every file to
/accounts/<id>/workers/assets/upload?base64=true and prints the completion JWT.
"""
import base64, hashlib, json, mimetypes, os, ssl, sys, urllib.request, urllib.error

ACC  = "42b2d98d9a78704a355c9a4f930c6065"
SITE = "/home/hermes/projects/blog-static/site"
URL  = f"https://api.cloudflare.com/client/v4/accounts/{ACC}/workers/assets/upload?base64=true"
CTX  = ssl.create_default_context()

jwt = open(sys.argv[1]).read().strip()
manifest = json.load(open("/tmp/manifest.json"))["manifest"]

boundary = "----hermes" + hashlib.md5(os.urandom(8)).hexdigest()
parts = []
for rel, meta in manifest.items():
    full = os.path.join(SITE, rel.lstrip("/"))
    data = open(full, "rb").read()
    assert len(data) == meta["size"], f"size mismatch {rel}"
    assert hashlib.sha256(data).hexdigest()[:32] == meta["hash"], f"hash mismatch {rel}"
    ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
    parts.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{meta["hash"]}"; filename="{os.path.basename(full)}"\r\n'
        f"Content-Type: {ctype}\r\n\r\n"
        f"{base64.b64encode(data).decode()}\r\n"
    )
body = "".join(parts) + f"--{boundary}--\r\n"

req = urllib.request.Request(URL, data=body.encode(), method="POST", headers={
    "Authorization": f"Bearer {jwt}",
    "Content-Type": f"multipart/form-data; boundary={boundary}",
})
try:
    with urllib.request.urlopen(req, timeout=180, context=CTX) as r:
        out = json.load(r)
        print("HTTP", r.status)
        print(json.dumps(out)[:600])
        if out.get("result", {}).get("jwt"):
            open("/tmp/completion_jwt.txt", "w").write(out["result"]["jwt"])
            print("completion jwt saved")
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    print(e.read()[:1000].decode())
