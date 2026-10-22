"""The other characters' frame lists, one file each in tools/specs/<id>.py
(each defines SPEC in the same format as AKUMA in extract_pocket.py)."""

import importlib
import os

ENEMIES = {}
_here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "specs")
for _f in sorted(os.listdir(_here)):
    if _f.endswith(".py") and not _f.startswith("_"):
        _cid = _f[:-3]
        ENEMIES[_cid] = importlib.import_module("specs." + _cid).SPEC
