#!/usr/bin/env bash
# =============================================================================
# BLAM - Toshi
# Arrow-key launcher for the scripts under $BLAM_DIR.
# Keys: Up/Down or k/j to move, 1-9/0 to jump, Home/End or g/G, Enter to run,
#       q or Esc to quit.
# =============================================================================

# --- PATHS (override with: BLAM_DIR=/some/where ./blam.sh) ---
BLAM_DIR="${BLAM_DIR:-/root/Z/USERS/Toshi/blam}"
SCRIPTS_DIR="$BLAM_DIR/blamscripts"
TWIDL_DIR="$BLAM_DIR/twidl"
TWIDL_INSTALL_DIR="/root/twidl"

# --- COLOR DEFINITIONS ---
RED=$'\e[0;31m'
GREEN=$'\e[0;32m'
PURPLE=$'\e[0;35m'
NOCOLOR=$'\e[0m'
HIGHLIGHT=$'\e[1;37;44m'  # Bold white on blue background
MENU_TEXT=$'\e[0;37m'

# -----------------------------------------------------------------------------
# 1) ASCII BANNER DEFINITION
# -----------------------------------------------------------------------------
# Centered as one block, so the letters stay aligned with each other.
ASCII_BANNER=(
"██████╗ ██╗      █████╗ ███╗   ███╗"
"██╔══██╗██║     ██╔══██╗████╗ ████║"
"██████╔╝██║     ███████║██╔████╔██║"
"██╔══██╗██║     ██╔══██║██║╚██╔╝██║"
"██████╔╝███████╗██║  ██║██║ ╚═╝ ██║"
"╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝"
)

# -----------------------------------------------------------------------------
# 2) MENU ENTRIES: "LABEL|action"
#    action is a script under $SCRIPTS_DIR, or a function name starting with "@".
# -----------------------------------------------------------------------------
MENU=(
    "FIO v2.1|FIO2.sh"
    "NVME-CLI v1.16|NVMECLI116.sh"
    "THINCLIENT|THINCLIENT.sh"
    "TWIDL|@install_twidl"
    "SST|SST.sh"
    "CLEAR AUTOMATION LOGS|clear_automation_logs.sh"
    "NO-MOTD|nomotd.sh"
    "CHANGE HOSTNAME|hostchange.sh"
    "INSTALL TOOLS|install.sh"
    "UNINSTALL TOOLS|uninstall.sh"
    "QUIT|@quit"
)
PROMPT_MSG="Use Arrow Keys to navigate & press Enter to select."

# -----------------------------------------------------------------------------
# 3) TERMINAL HANDLING
# -----------------------------------------------------------------------------
STTY_SAVED=""
TERM_COLS=80

# Visible width of a UTF-8 string, independent of the current locale:
# count every byte that is not a UTF-8 continuation byte (0x80-0xBF).
str_width() {
    local LC_ALL=C s="$1"
    s=${s//[$'\x80'-$'\xbf']/}
    printf -v "$2" '%d' "${#s}"
}

update_size() {
    local cols
    cols=$(tput cols 2>/dev/null) || cols=""
    [[ $cols =~ ^[0-9]+$ ]] && (( cols > 0 )) || cols=${COLUMNS:-80}
    TERM_COLS=$cols
}

menu_mode_on() {
    [[ -t 0 ]] && STTY_SAVED=$(stty -g 2>/dev/null) && stty -echo -icanon 2>/dev/null
    printf '\e[?25l'           # hide cursor
}

menu_mode_off() {
    [[ -n $STTY_SAVED ]] && stty "$STTY_SAVED" 2>/dev/null
    STTY_SAVED=""
    printf '\e[?25h%s' "$NOCOLOR"   # show cursor, reset colors
}

cleanup() { menu_mode_off; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
trap 'NEED_RESIZE=1' WINCH

# -----------------------------------------------------------------------------
# 4) DRAWING
# -----------------------------------------------------------------------------
BANNER_WIDTH=0
MENU_WIDTH=0
LABELS=()

prepare() {
    local line w i
    for line in "${ASCII_BANNER[@]}"; do
        str_width "$line" w
        (( w > BANNER_WIDTH )) && BANNER_WIDTH=$w
    done
    LABELS=()
    for i in "${!MENU[@]}"; do
        LABELS[i]="${MENU[i]%%|*}"
        str_width "${LABELS[i]}" w
        (( w + 6 > MENU_WIDTH )) && MENU_WIDTH=$(( w + 6 ))   # "> NN. " prefix
    done
}

# Pad needed to center something of width $1, written to var $2.
center_pad() {
    local p=$(( (TERM_COLS - $1) / 2 ))
    (( p < 0 )) && p=0
    printf -v "$2" '%d' "$p"
}

# Builds the whole screen in one buffer and writes it once (no flicker).
draw() {
    local cur=$1 buf="" pad line i num item
    buf+=$'\e[H'
    center_pad "$BANNER_WIDTH" pad
    buf+=$'\e[K\n'"$PURPLE"
    for line in "${ASCII_BANNER[@]}"; do
        printf -v line '%*s%s' "$pad" "" "$line"
        buf+="$line"$'\e[K\n'
    done
    buf+="$NOCOLOR"$'\e[K\n'
    str_width "$PROMPT_MSG" i
    center_pad "$i" pad
    printf -v line '%*s%s' "$pad" "" "$PROMPT_MSG"
    buf+="$line"$'\e[K\n\e[K\n'

    center_pad "$MENU_WIDTH" pad
    for i in "${!LABELS[@]}"; do
        if (( i < 10 )); then num="$(( (i + 1) % 10 ))."; else num="  "; fi
        if (( i == cur )); then
            printf -v item '> %s %s' "$num" "${LABELS[i]}"
            printf -v item '%-*s' "$MENU_WIDTH" "$item"
            printf -v line '%*s%s%s%s' "$pad" "" "$HIGHLIGHT" "$item" "$NOCOLOR"
        else
            printf -v item '  %s %s' "$num" "${LABELS[i]}"
            printf -v item '%-*s' "$MENU_WIDTH" "$item"
            printf -v line '%*s%s%s%s' "$pad" "" "$MENU_TEXT" "$item" "$NOCOLOR"
        fi
        buf+="$line"$'\e[K\n'
    done
    buf+=$'\e[J'
    printf '%s' "$buf"
}

# -----------------------------------------------------------------------------
# 5) INPUT
# -----------------------------------------------------------------------------
# Reads one keypress into var $1 as a name: up, down, home, end, enter, quit,
# digit:N, or other. Returns 1 if the read was interrupted (e.g. resize).
read_key() {
    local k rest="" rc
    IFS= read -rsn1 k; rc=$?
    if (( rc > 128 )); then printf -v "$1" 'none'; return 1; fi
    (( rc != 0 )) && { printf -v "$1" 'quit'; return 0; }   # EOF: stdin closed
    if [[ $k == $'\e' ]]; then
        # Escape sequence: gather the rest quickly; a lone Esc means quit.
        IFS= read -rsn1 -t 0.05 k || { printf -v "$1" 'quit'; return 0; }
        rest=$k
        if [[ $k == '[' || $k == 'O' ]]; then
            while IFS= read -rsn1 -t 0.05 k; do
                rest+=$k
                [[ $k == [A-Za-z~] ]] && break
            done
        fi
        case $rest in
            '[A'|'OA') k=up ;;
            '[B'|'OB') k=down ;;
            '[H'|'OH'|'[1~'|'[7~') k=home ;;
            '[F'|'OF'|'[4~'|'[8~') k=end ;;
            '[5~') k=home ;;   # PgUp
            '[6~') k=end ;;    # PgDn
            *) k=other ;;
        esac
    else
        case $k in
            ''|$'\n'|$'\r') k=enter ;;
            k|K) k=up ;;
            j|J) k=down ;;
            g) k=home ;;
            G) k=end ;;
            q|Q) k=quit ;;
            [0-9]) k="digit:$k" ;;
            *) k=other ;;
        esac
    fi
    printf -v "$1" '%s' "$k"
}

# Shows the menu; puts the chosen index in var $1 (or -1 for quit).
choose_from_menu() {
    local outvar=$1 cur=${2:-0} count=${#LABELS[@]} key n
    NEED_RESIZE=1
    printf '\e[H\e[2J'
    while true; do
        if (( NEED_RESIZE )); then
            NEED_RESIZE=0
            update_size
            printf '\e[2J'
        fi
        draw "$cur"
        read_key key || continue
        case $key in
            up)    cur=$(( (cur - 1 + count) % count )) ;;
            down)  cur=$(( (cur + 1) % count )) ;;
            home)  cur=0 ;;
            end)   cur=$(( count - 1 )) ;;
            enter) break ;;
            quit)  cur=-1; break ;;
            digit:*)
                n=${key#digit:}
                (( n == 0 )) && n=10
                (( n <= count )) && { cur=$(( n - 1 )); draw "$cur"; break; }
                ;;
        esac
    done
    printf -v "$outvar" '%d' "$cur"
}

# -----------------------------------------------------------------------------
# 6) ACTIONS
# -----------------------------------------------------------------------------
die_msg() { printf '%s%s%s\n' "$RED" "$*" "$NOCOLOR"; return 1; }

run_script() {
    local path="$SCRIPTS_DIR/$1"
    [[ -f $path ]] || { die_msg "Script not found: $path"; return; }
    if [[ -x $path ]]; then
        "$path"
    else
        # Not executable: run it with bash instead of failing.
        bash "$path"
    fi
}

install_twidl() {
    local installers=() installer
    shopt -s nullglob
    installers=("$TWIDL_DIR"/TWIDL_*_Installer_Linux.sh)
    shopt -u nullglob
    if (( ${#installers[@]} == 0 )); then
        die_msg "No TWIDL installer found in $TWIDL_DIR"
        return
    fi
    # Pick the highest version if there are several.
    installer=$(printf '%s\n' "${installers[@]}" | sort -V | tail -n 1)
    echo "Using $installer"
    chmod +x "$installer" || return
    "$installer" || return
    if [[ -d $TWIDL_INSTALL_DIR ]]; then
        chmod +x "$TWIDL_INSTALL_DIR"/* 2>/dev/null
    fi
}

quit() {
    printf '%s Exiting... %s\n' "$PURPLE" "$NOCOLOR"
    exit 0
}

run_action() {
    local idx=$1 label action rc
    label=${MENU[idx]%%|*}
    action=${MENU[idx]#*|}
    [[ $action == "@quit" ]] && quit

    clear
    printf '%s>>> %s%s\n\n' "$PURPLE" "$label" "$NOCOLOR"
    # Ctrl-C now stops the running script but brings you back to the menu.
    trap ':' INT
    if [[ $action == @* ]]; then
        "${action#@}"
    else
        run_script "$action"
    fi
    rc=$?
    trap 'exit 130' INT

    echo
    if (( rc == 0 )); then
        printf '%s%s finished.%s\n' "$GREEN" "$label" "$NOCOLOR"
    else
        printf '%s%s exited with code %d.%s\n' "$RED" "$label" "$rc" "$NOCOLOR"
    fi
    printf 'Press any key to return to the menu...'
    IFS= read -rsn1 _ || exit 0
}

# -----------------------------------------------------------------------------
# 7) MAIN LOOP
# -----------------------------------------------------------------------------
main() {
    if [[ ! -t 0 || ! -t 1 ]]; then
        echo "blam needs an interactive terminal." >&2
        exit 1
    fi
    prepare
    local choice last=0
    while true; do
        menu_mode_on
        choose_from_menu choice "$last"
        menu_mode_off
        (( choice < 0 )) && quit
        last=$choice
        run_action "$choice"
    done
}

main "$@"
