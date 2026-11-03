#!/bin/sh
# Build the browser version of Akuma Quest with pygbag (https://pygame-web.github.io).
#   pip install pygbag
#   sh web/build.sh            -> play/ (index.html + akuma-quest.apk), served by GitHub Pages
#   sh web/build.sh --serve    -> also starts a local test server on http://localhost:8000
# Extra args go to pygbag (e.g. --cdn http://localhost:8001/archives/0.9/ for an offline CDN copy).
set -e
cd "$(dirname "$0")/.."
SERVE=0
if [ "$1" = "--serve" ]; then SERVE=1; shift; fi
STAGE=build/web-stage/akuma-quest
rm -rf build/web-stage
mkdir -p "$STAGE"
# only what the game needs at run time: no tests, tools, source art or screenshots
cp main.py "$STAGE/"
cp -r akuma "$STAGE/akuma"
find "$STAGE" -name __pycache__ -type d -prune -exec rm -rf {} +
cp web/favicon.png "$STAGE/favicon.png"
# --no_opt: keep the sprites lossless (pygbag's optimizer runs pngquant)
python3 -m pygbag --build --no_opt --title "Akuma Quest" --app_name akuma-quest --ume_block 1 "$@" "$STAGE"
rm -rf play
mkdir -p play
cp "$STAGE/build/web/akuma-quest.apk" play/
# crisp pixel art when the 320x180 canvas is scaled up to the window
sed 's#</head>#<style>canvas{image-rendering:pixelated;image-rendering:crisp-edges}</style></head>#' \
    "$STAGE/build/web/index.html" > play/index.html
cp web/favicon.png play/favicon.png
echo "built play/ ($(du -sh play | cut -f1))"
if [ $SERVE = 1 ]; then cd play && python3 -m http.server 8000; fi
