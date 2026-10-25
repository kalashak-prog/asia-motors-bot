#!/usr/bin/env python3
import zlib, base64
from pathlib import Path
parts = []
for i in range(20):
    p = Path(f"chunk_{i:02d}.txt")
    if not p.exists():
        break
    t = p.read_text().strip()
    if not t:
        break
    parts.append(t)
b64 = "".join(parts)
Path("bot.py").write_bytes(zlib.decompress(base64.b64decode(b64)))
print("bot.py restored", Path("bot.py").stat().st_size, "from", len(parts), "chunks")
