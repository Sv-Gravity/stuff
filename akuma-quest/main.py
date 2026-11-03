#!/usr/bin/env python3
"""Akuma Quest. Run with:  python main.py   (add --fullscreen for full screen)

The same file is the entry point of the browser build (web/build.sh, pygbag).
"""

# pygbag reads this block to fetch numpy for the browser build (levels 12-13 need it)
# /// script
# dependencies = [
#   "numpy",
# ]
# ///

import sys

if sys.platform == "emscripten":
    import asyncio
    import importlib

    import pygame

    # the browser runtime imports pygame before numpy is installed, so pygame.surfarray
    # starts out as a "missing module" stub; load the real one now (levels 12-13 need it)
    for _m in ("surfarray", "sndarray"):
        try:
            setattr(pygame, _m, importlib.import_module("pygame." + _m))
        except Exception as e:
            print("pygame.%s unavailable: %r" % (_m, e))

    from akuma.game import main_web

    asyncio.run(main_web())
else:
    from akuma.game import main

    if __name__ == "__main__":
        main()
