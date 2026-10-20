#!/usr/bin/env bash
# =============================================================================
# FANCY BLAM - Toshi
# blam, dealt out as a hand of cards on a felt table. Every card is a menu
# entry; the selected card lifts off the table and lights up.
# Keys: Arrows or h/j/k/l to move between cards, 1-9/0 to jump straight to a
#       card, Home/End or g/G, Enter to play the card, q or Esc to fold (quit).
#       Any key skips the deal animation.
# =============================================================================

# --- PATHS (override with: BLAM_DIR=/some/where ./fancy_blam.sh) ---
BLAM_DIR="${BLAM_DIR:-/root/Z/USERS/Toshi/blam}"
SCRIPTS_DIR="$BLAM_DIR/blamscripts"
TWIDL_DIR="$BLAM_DIR/twidl"
TWIDL_INSTALL_DIR="/root/twidl"

# --- COLOR DEFINITIONS (used outside the card table) ---
RED=$'\e[0;31m'
GREEN=$'\e[0;32m'
PURPLE=$'\e[0;35m'
NOCOLOR=$'\e[0m'

# -----------------------------------------------------------------------------
# 1) ASCII BANNER DEFINITION
# -----------------------------------------------------------------------------
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
#    Cards are dealt A, 2, 3 ... in this order; the @quit entry is the Joker.
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
TAGLINE="pick a card, any card"
HINT="←↑↓→ move   Enter play card   1-9 jump   q fold"

RANKS=(A 2 3 4 5 6 7 8 9 10 J Q K)
SUITS=("♠" "♥" "♣" "♦")

# -----------------------------------------------------------------------------
# 3) TABLE COLORS (256 colors, with an 8-color fallback)
# -----------------------------------------------------------------------------
RS=$'\e[0m'
if (( $(tput colors 2>/dev/null || echo 8) >= 256 )); then
    FELT=$'\e[48;5;22m'            # green table
    FELT_TEXT=$'\e[38;5;194m'
    GOLD=$'\e[1;38;5;220m'
    FACE=$'\e[48;5;231m'           # card face
    SEL_FACE=$'\e[48;5;230m'       # selected card face
    BORDER=$'\e[38;5;244m'
    SEL_BORDER=$'\e[1;38;5;214m'
    INK=$'\e[38;5;16m'
    SEL_INK=$'\e[1;38;5;16m'
    RED_INK=$'\e[38;5;160m'
    JOKER_INK=$'\e[38;5;129m'
    BACK_INK=$'\e[38;5;25m'
    SHADOW=$'\e[38;5;234m'
else
    FELT=$'\e[42m'
    FELT_TEXT=$'\e[37m'
    GOLD=$'\e[1;33m'
    FACE=$'\e[47m'
    SEL_FACE=$'\e[43m'
    BORDER=$'\e[30m'
    SEL_BORDER=$'\e[1;31m'
    INK=$'\e[30m'
    SEL_INK=$'\e[1;30m'
    RED_INK=$'\e[31m'
    JOKER_INK=$'\e[35m'
    BACK_INK=$'\e[34m'
    SHADOW=$'\e[30m'
fi

# -----------------------------------------------------------------------------
# 4) TERMINAL HANDLING
# -----------------------------------------------------------------------------
STTY_SAVED=""
TERM_COLS=80
TERM_LINES=24

# Visible width of a UTF-8 string, independent of the current locale:
# count every byte that is not a UTF-8 continuation byte (0x80-0xBF).
str_width() {
    local LC_ALL=C s="$1"
    s=${s//[$'\x80'-$'\xbf']/}
    printf -v "$2" '%d' "${#s}"
}

update_size() {
    local cols lines
    cols=$(tput cols 2>/dev/null) || cols=""
    lines=$(tput lines 2>/dev/null) || lines=""
    [[ $cols =~ ^[0-9]+$ ]] && (( cols > 0 )) || cols=${COLUMNS:-80}
    [[ $lines =~ ^[0-9]+$ ]] && (( lines > 0 )) || lines=${LINES:-24}
    TERM_COLS=$cols
    TERM_LINES=$lines
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
# 5) THE DECK
# -----------------------------------------------------------------------------
LABELS=()
CORNERS=()      # "A♠", "10♥", "★" ...
CORNER_INK=()
WRAP=()         # word-wrapped label, 3 lines per card: WRAP[i*3+j]
WRAP_N=()
BANNER_WIDTH=0

CARD_W=18       # card size, including its border
CARD_H=9
GAP=2           # felt between cards
COLS_N=1        # cards per row
ROWS_N=1
SHOW_BANNER=1
HL_THIN=""      # top/bottom border runs, CARD_W-2 wide
HL_THICK=""
BACK_A=""       # card back pattern lines
BACK_B=""

# Word-wraps "$1" into at most 3 lines of width $2, for card $3.
wrap_label() {
    local text=$1 width=$2 idx=$3 word line="" n=0 w lw
    for word in $text; do
        str_width "$word" w
        (( w > width )) && { word=${word:0:width}; w=$width; }
        str_width "$line" lw
        if [[ -z $line ]]; then
            line=$word
        elif (( lw + 1 + w <= width )); then
            line+=" $word"
        else
            (( n < 3 )) && WRAP[idx*3+n]=$line
            (( n++ ))
            line=$word
        fi
    done
    [[ -n $line ]] && { (( n < 3 )) && WRAP[idx*3+n]=$line; (( n++ )); }
    (( n > 3 )) && n=3
    WRAP_N[idx]=$n
}

prepare() {
    local line w i action
    for line in "${ASCII_BANNER[@]}"; do
        str_width "$line" w
        (( w > BANNER_WIDTH )) && BANNER_WIDTH=$w
    done
    LABELS=()
    for i in "${!MENU[@]}"; do
        LABELS[i]="${MENU[i]%%|*}"
        action=${MENU[i]#*|}
        if [[ $action == "@quit" ]]; then
            CORNERS[i]="★"
            CORNER_INK[i]=$JOKER_INK
        else
            CORNERS[i]="${RANKS[i % 13]}${SUITS[i % 4]}"
            if (( i % 2 )); then CORNER_INK[i]=$RED_INK; else CORNER_INK[i]=$INK; fi
        fi
        wrap_label "${LABELS[i]}" $(( CARD_W - 4 )) "$i"
    done
    local inner=$(( CARD_W - 2 ))
    printf -v HL_THIN '%*s' "$inner" ''
    HL_THICK=${HL_THIN// /━}
    HL_THIN=${HL_THIN// /─}
    BACK_A="" BACK_B=""
    for (( i = 0; i < inner; i++ )); do
        if (( i % 2 )); then BACK_A+="╲"; BACK_B+="╱"; else BACK_A+="╱"; BACK_B+="╲"; fi
    done
}

# Picks card height, cards per row and whether the big banner fits.
# Short terminals get shorter cards; 5-line cards drop the corner indices.
layout() {
    local n=${#LABELS[@]} opt h banner header need c
    for opt in "9 1" "9 0" "7 0" "5 0"; do
        read -r h banner <<< "$opt"
        c=$(( (TERM_COLS - 2 + GAP) / (CARD_W + GAP) ))
        (( c < 1 )) && c=1
        (( c > n )) && c=$n
        ROWS_N=$(( (n + c - 1) / c ))
        COLS_N=$(( (n + ROWS_N - 1) / ROWS_N ))   # balance the rows
        if (( banner )); then header=9; else header=2; fi
        need=$(( header + ROWS_N * (h + 1) + 2 ))
        (( need <= TERM_LINES )) && break
    done
    CARD_H=$h
    SHOW_BANNER=$banner
}

# Column (in cells, relative to the table's left edge) where card $1 sits.
# A short last row is centered under the rows above it.
card_x() {
    local i=$1 r c inrow n=${#LABELS[@]}
    r=$(( i / COLS_N )); c=$(( i % COLS_N ))
    inrow=$(( n - r * COLS_N )); (( inrow > COLS_N )) && inrow=$COLS_N
    printf -v "$2" '%d' $(( (COLS_N - inrow) * (CARD_W + GAP) / 2 + c * (CARD_W + GAP) ))
}

# -----------------------------------------------------------------------------
# 6) DRAWING
# -----------------------------------------------------------------------------
# Line $2 (0..CARD_H-1) of card $1 into CL. State $3: 0 face up, 1 selected,
# 2 face down (the flip when a card is played).
card_line() {
    local i=$1 l=$2 st=$3 inner=$(( CARD_W - 2 )) fc bc ink v tl tr bl br hl
    local body="" w pad lp start
    if (( st == 1 )); then
        fc=$SEL_FACE bc=$SEL_BORDER ink=$SEL_INK v='┃' tl='┏' tr='┓' bl='┗' br='┛' hl=$HL_THICK
    else
        fc=$FACE bc=$BORDER ink=$INK v='│' tl='╭' tr='╮' bl='╰' br='╯' hl=$HL_THIN
    fi
    if (( l == 0 )); then CL="$RS$fc$bc$tl$hl$tr"; return; fi
    if (( l == CARD_H - 1 )); then CL="$RS$fc$bc$bl$hl$br"; return; fi

    if (( st == 2 )); then
        if (( l % 2 )); then body="$RS$fc$BACK_INK$BACK_A"; else body="$RS$fc$BACK_INK$BACK_B"; fi
    elif (( CARD_H >= 7 && l == 1 )); then
        str_width "${CORNERS[i]}" w
        printf -v pad '%*s' $(( inner - 1 - w )) ''
        body="$RS$fc ${CORNER_INK[i]}${CORNERS[i]}$RS$fc$pad"
    elif (( CARD_H >= 7 && l == CARD_H - 2 )); then
        str_width "${CORNERS[i]}" w
        printf -v pad '%*s' $(( inner - 1 - w )) ''
        body="$RS$fc$pad${CORNER_INK[i]}${CORNERS[i]}$RS$fc "
    else
        # Label area sits between the corners; center the wrapped label in it.
        local top=2 area=$(( CARD_H - 4 ))
        (( CARD_H < 7 )) && { top=1; area=$(( CARD_H - 2 )); }
        start=$(( top + (area - WRAP_N[i]) / 2 ))
        if (( l >= start && l < start + WRAP_N[i] )); then
            local text=${WRAP[i * 3 + l - start]}
            str_width "$text" w
            lp=$(( (inner - w) / 2 ))
            printf -v body '%*s%s%*s' "$lp" '' "$text" $(( inner - w - lp )) ''
            body="$RS$fc$ink$body"
        else
            printf -v body '%*s' "$inner" ''
            body="$RS$fc$body"
        fi
    fi
    CL="$RS$fc$bc$v$body$RS$fc$bc$v"
}

# Draws the table. $1 selected card, $2 how many cards are dealt so far,
# $3 card shown face down (-1 for none). One write per frame, no flicker.
draw() {
    local cur=$1 shown=${2:-${#LABELS[@]}} flip=${3:--1}
    local n=${#LABELS[@]} buf lines=() line pad i r sl l x col st w tw
    local slot=$(( CARD_H + 1 ))

    # Header
    if (( SHOW_BANNER )); then
        lines+=("")
        pad=$(( (TERM_COLS - BANNER_WIDTH) / 2 )); (( pad < 0 )) && pad=0
        for line in "${ASCII_BANNER[@]}"; do
            printf -v line '%*s%s' "$pad" '' "$line"
            lines+=("$GOLD$line$RS$FELT")
        done
    fi
    local plain="♠ ♥  F A N C Y   B L A M  ♣ ♦   ·   $TAGLINE"
    (( SHOW_BANNER )) && plain="♠ ♥ ♣ ♦   $TAGLINE   ♦ ♣ ♥ ♠"
    str_width "$plain" w
    pad=$(( (TERM_COLS - w) / 2 )); (( pad < 0 )) && pad=0
    printf -v line '%*s' "$pad" ''
    lines+=("$line$FELT_TEXT$plain$RS$FELT")
    lines+=("")

    # The cards
    tw=$(( COLS_N * CARD_W + (COLS_N - 1) * GAP ))
    pad=$(( (TERM_COLS - tw) / 2 )); (( pad < 0 )) && pad=0
    for (( r = 0; r < ROWS_N; r++ )); do
        for (( sl = 0; sl < slot; sl++ )); do
            line="" col=0
            for (( i = r * COLS_N; i < (r + 1) * COLS_N && i < n; i++ )); do
                (( i >= shown )) && continue
                card_x "$i" x
                printf -v w '%*s' $(( pad + x - col )) ''
                line+="$RS$FELT$w"
                col=$(( pad + x + CARD_W ))
                st=0; (( i == cur )) && st=1; (( i == flip )) && st=2
                # The selected card is lifted one line, with a shadow under it.
                if (( i == cur )); then l=$sl; else l=$(( sl - 1 )); fi
                if (( l < 0 )); then
                    printf -v w '%*s' "$CARD_W" ''
                    line+="$RS$FELT$w"
                elif (( l == CARD_H )); then
                    printf -v w '%*s' $(( CARD_W - 1 )) ''
                    line+="$RS$FELT $SHADOW${w// /▀}"
                else
                    card_line "$i" "$l" "$st"
                    line+=$CL
                fi
            done
            lines+=("$line$RS$FELT")
        done
    done

    # Footer
    lines+=("")
    str_width "$HINT" w
    pad=$(( (TERM_COLS - w) / 2 )); (( pad < 0 )) && pad=0
    printf -v line '%*s%s' "$pad" '' "$HINT"
    lines+=("$FELT_TEXT$line$RS$FELT")

    # Never write past the last line, or the terminal would scroll.
    buf=$'\e[H'"$RS$FELT"
    for (( i = 0; i < ${#lines[@]} && i < TERM_LINES; i++ )); do
        (( i > 0 )) && buf+=$'\n'
        buf+="$FELT${lines[i]}"$'\e[K'
    done
    buf+=$'\e[J'
    printf '%s' "$buf"
}

# -----------------------------------------------------------------------------
# 7) INPUT
# -----------------------------------------------------------------------------
# Reads one keypress into var $1 as a name: up, down, left, right, home, end,
# enter, quit, digit:N, or other. Returns 1 if the terminal was resized.
read_key() {
    local k rest="" rc
    # Wake up now and then so a terminal resize redraws without a keypress.
    while true; do
        IFS= read -rsn1 -t 0.25 k; rc=$?
        (( rc > 128 )) || break
        (( NEED_RESIZE )) && { printf -v "$1" 'none'; return 1; }
    done
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
            '[C'|'OC') k=right ;;
            '[D'|'OD') k=left ;;
            '[H'|'OH'|'[1~'|'[7~'|'[5~') k=home ;;
            '[F'|'OF'|'[4~'|'[8~'|'[6~') k=end ;;
            *) k=other ;;
        esac
    else
        case $k in
            ''|$'\n'|$'\r') k=enter ;;
            k|K) k=up ;;
            j|J) k=down ;;
            h|H) k=left ;;
            l|L) k=right ;;
            g) k=home ;;
            G) k=end ;;
            q|Q) k=quit ;;
            [0-9]) k="digit:$k" ;;
            *) k=other ;;
        esac
    fi
    printf -v "$1" '%s' "$k"
}

# Moves from card $1 one row by $2 (-1 up, +1 down, wrapping around), landing
# on the card closest to the same column. Result in var $3.
move_row() {
    local from=$1 dir=$2 n=${#LABELS[@]} r tr x tx j best=-1 bd d
    r=$(( from / COLS_N ))
    tr=$(( (r + dir + ROWS_N) % ROWS_N ))
    card_x "$from" x
    for (( j = tr * COLS_N; j < (tr + 1) * COLS_N && j < n; j++ )); do
        card_x "$j" tx
        d=$(( tx - x )); (( d < 0 )) && d=$(( -d ))
        if (( best < 0 || d < bd )); then best=$j; bd=$d; fi
    done
    printf -v "$3" '%d' "$best"
}

# Brief pause that any key cuts short. Returns 0 if a key was pressed.
pause() { IFS= read -rsn1 -t "$1" _; }

DEALT=0

# Deals the table; puts the chosen index in var $1 (or -1 for quit).
choose_from_menu() {
    local outvar=$1 cur=${2:-0} count=${#LABELS[@]} key n d
    NEED_RESIZE=1
    printf '%s\e[H\e[2J' "$FELT"
    while true; do
        if (( NEED_RESIZE )); then
            NEED_RESIZE=0
            update_size
            layout
            printf '%s\e[2J' "$FELT"
        fi
        if (( ! DEALT )); then
            DEALT=1
            for (( d = 1; d <= count; d++ )); do
                draw "$cur" "$d"
                pause 0.06 && break
            done
        fi
        draw "$cur"
        read_key key || continue
        case $key in
            left)  cur=$(( (cur - 1 + count) % count )) ;;
            right) cur=$(( (cur + 1) % count )) ;;
            up)    move_row "$cur" -1 cur ;;
            down)  move_row "$cur" 1 cur ;;
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
    if (( cur >= 0 )); then
        # Flip the played card over before running it.
        draw "$cur" "$count" "$cur"; pause 0.25
        draw "$cur"; pause 0.1
    fi
    printf -v "$outvar" '%d' "$cur"
}

# -----------------------------------------------------------------------------
# 8) ACTIONS
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
    printf '%s\e[H\e[2J' "$NOCOLOR"   # clear the felt off the screen
    printf '%s Folding... thanks for playing. %s\n' "$PURPLE" "$NOCOLOR"
    exit 0
}

run_action() {
    local idx=$1 label action rc
    label=${MENU[idx]%%|*}
    action=${MENU[idx]#*|}
    [[ $action == "@quit" ]] && quit

    printf '%s' "$NOCOLOR"
    clear
    printf '%s>>> %s %s%s\n\n' "$PURPLE" "${CORNERS[idx]}" "$label" "$NOCOLOR"
    # Ctrl-C now stops the running script but brings you back to the table.
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
    printf 'Press any key to return to the table...'
    IFS= read -rsn1 _ || exit 0
}

# -----------------------------------------------------------------------------
# 9) MAIN LOOP
# -----------------------------------------------------------------------------
main() {
    if [[ ! -t 0 || ! -t 1 ]]; then
        echo "fancy_blam needs an interactive terminal." >&2
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
