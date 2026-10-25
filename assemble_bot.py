#!/usr/bin/env python3
import zlib, base64
from pathlib import Path
parts = []
i = 0
while True:
    p = Path(f"chunk_{i:02d}.txt")
    if not p.exists():
        break
    parts.append(p.read_text().strip())
    i += 1
b64 = "".join(parts)
Path("bot.py").write_bytes(zlib.decompress(base64.b64decode(b64)))
print("bot.py restored", Path("bot.py").stat().st_size, "from", i, "chunks")
