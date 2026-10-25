#!/usr/bin/env python3
import zlib, base64
from pathlib import Path
p1 = Path("bot_p1.txt").read_text().strip()
p2 = Path("bot_p2.txt").read_text().strip()
Path("bot.py").write_bytes(zlib.decompress(base64.b64decode(p1+p2)))
print("bot.py restored", Path("bot.py").stat().st_size)
