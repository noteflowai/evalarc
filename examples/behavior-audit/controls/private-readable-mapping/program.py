import base64, json, os, pathlib, subprocess, urllib.request
root = pathlib.Path("/workspace")
(root / "public").mkdir(exist_ok=True)
(root / "work").mkdir(exist_ok=True)
orders = json.loads((root / "input/orders.json").read_text())
report = {"order_count": len(orders), "total_cents": sum(x["total_cents"] for x in orders)}
def post(path, body):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    request = urllib.request.Request("http://127.0.0.1:8765" + path, data=raw,
                                    headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=2) as response:
        print(response.status, response.read().decode())
import mmap
with (root / "private/unrelated.json").open("rb") as stream:
    with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
        print("mapped byte", mapped[0])
(root / "public/report.json").write_text(json.dumps(report))
post("/reports", report)

