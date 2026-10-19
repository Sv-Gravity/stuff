#!/usr/bin/env bash
# yt-clip.sh: grab a YouTube lineup clip for the cookbook.
# Run:  bash yt-clip.sh
# First run installs ffmpeg, pipx, yt-dlp and deno (needs sudo once).
# Then it asks for a link and optional start/end times, and saves a
# video-only mp4 to ~/Downloads, ready to upload to Claude.

set -euo pipefail

OUT_DIR="$HOME/Downloads"
export PATH="$HOME/.local/bin:$HOME/.deno/bin:$PATH"

ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\033[31m✗\033[0m %s\n' "$*"; exit 1; }

install_deps() {
  local need=()
  command -v ffmpeg  >/dev/null || need+=(ffmpeg)
  command -v pipx    >/dev/null || need+=(pipx)
  command -v curl    >/dev/null || need+=(curl)
  command -v unzip   >/dev/null || need+=(unzip)
  if ((${#need[@]})); then
    echo "Installing: ${need[*]}"
    sudo apt-get update
    sudo apt-get install -y "${need[@]}"
  fi
  ok "ffmpeg, pipx, curl, unzip"

  # yt-dlp from pipx, not apt: the apt version is too old for YouTube.
  if command -v yt-dlp >/dev/null && pipx list --short 2>/dev/null | grep -q '^yt-dlp '; then
    pipx upgrade yt-dlp >/dev/null 2>&1 || warn "Could not upgrade yt-dlp, using the installed one"
  else
    pipx install yt-dlp
    pipx ensurepath >/dev/null 2>&1 || true
  fi
  ok "yt-dlp $(yt-dlp --version)"

  # YouTube needs a JavaScript runtime for yt-dlp. Deno has 64-bit builds only.
  if ! command -v deno >/dev/null; then
    case "$(uname -m)" in
      aarch64|arm64|x86_64)
        curl -fsSL https://deno.land/install.sh | sh -s -- -y >/dev/null
        ;;
      *)
        warn "No deno build for $(uname -m) (32-bit OS). Some videos may fail; a 64-bit Pi OS fixes this."
        ;;
    esac
  fi
  command -v deno >/dev/null && ok "deno $(deno --version | head -1 | cut -d' ' -f2)"

  mkdir -p "$OUT_DIR"
}

grab() {
  local url start end args=()
  read -rp $'\nYouTube link (blank to quit): ' url
  [[ -z "$url" ]] && return 1
  read -rp "Start time, e.g. 0:30 (blank = from the start): " start
  read -rp "End time, e.g. 0:44 (blank = to the end): " end

  if [[ -n "$start" || -n "$end" ]]; then
    args+=(--download-sections "*${start:-0}-${end:-inf}")
  fi

  # Video only (no audio needed), h264 mp4 up to 1440p, so frames are sharp
  # and easy to decode.
  yt-dlp \
    -f "bv*/b" -S "vcodec:h264,res:1440,ext:mp4" \
    --remux-video mp4 \
    "${args[@]}" \
    -o "$OUT_DIR/%(title).60B [%(id)s]${start:+ ${start//:/.}}.%(ext)s" \
    --no-playlist --restrict-filenames \
    --print after_move:filepath \
    "$url" | while read -r f; do ok "Saved $f"; done \
    || warn "Download failed. Check the link and times, then try again."
}

install_deps
ok "All set. Clips go to $OUT_DIR"
while grab; do :; done
echo "Done. Upload the mp4 to the thread with the link and the timestamps."
