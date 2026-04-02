#!/usr/bin/env bash
# =============================================================================
# scripts/make_gif.sh — Producera demo-GIF för NoUse README
# =============================================================================
#
# Kräver:
#   asciinema   pip install asciinema
#   agg         https://github.com/asciinema/agg  (se installation nedan)
#   rich        pip install rich   (för demo.py)
#
# Kör:
#   cd /home/bjorn/projects/nouse
#   bash scripts/make_gif.sh
#
# Output:
#   IMG/demo.gif   — klar för README
#   IMG/demo.cast  — råinspelning (kan laddas upp till asciinema.org)
#
# =============================================================================

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CAST_FILE="$REPO_ROOT/IMG/demo.cast"
GIF_FILE="$REPO_ROOT/IMG/demo.gif"
DEMO_SCRIPT="$REPO_ROOT/scripts/demo.py"

# ── Färger ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'

echo -e "${BOLD}${CYAN}"
echo "  ███╗   ██╗ ██████╗ ██╗   ██╗███████╗███████╗"
echo "  ████╗  ██║██╔═══██╗██║   ██║██╔════╝██╔════╝"
echo "  ██╔██╗ ██║██║   ██║██║   ██║███████╗█████╗  "
echo "  ██║╚██╗██║██║   ██║██║   ██║╚════██║██╔══╝  "
echo "  ██║ ╚████║╚██████╔╝╚██████╔╝███████║███████╗"
echo "  ╚═╝  ╚═══╝ ╚═════╝  ╚═════╝ ╚══════╝╚══════╝"
echo -e "${NC}${BOLD}  GIF-producent — den plastiska hjärnan${NC}"
echo ""

# ── Kontrollera beroenden ─────────────────────────────────────────────────────
check_dep() {
    local cmd="$1" install_hint="$2"
    if ! command -v "$cmd" &>/dev/null; then
        echo -e "${RED}✗ Saknar: $cmd${NC}"
        echo -e "  ${YELLOW}Installera: $install_hint${NC}"
        return 1
    fi
    echo -e "${GREEN}✓ $cmd$(command -v $cmd | xargs 2>/dev/null)${NC}"
}

echo -e "${BOLD}Kontrollerar beroenden...${NC}"
MISSING=0

check_dep asciinema "pip install asciinema" || MISSING=1
check_dep python    "https://python.org"    || MISSING=1

# agg är valfritt — faller tillbaka på alternativ
AGG_CMD=""
if command -v agg &>/dev/null; then
    AGG_CMD="agg"
    echo -e "${GREEN}✓ agg (asciinema→gif)${NC}"
elif command -v docker &>/dev/null; then
    AGG_CMD="docker"
    echo -e "${YELLOW}⚠ agg ej installerat — använder Docker-fallback${NC}"
else
    echo -e "${YELLOW}⚠ agg ej installerat${NC}"
    echo -e "  ${YELLOW}Installera (en av):"
    echo -e "    cargo install --git https://github.com/asciinema/agg"
    echo -e "    brew install agg   (macOS)"
    echo -e "    Binärer: https://github.com/asciinema/agg/releases${NC}"
    echo ""
    echo -e "  ${CYAN}Scriptet producerar ändå .cast-filen."
    echo -e "  Ladda upp till https://asciinema.org för delning, eller"
    echo -e "  installera agg och kör igen för GIF.${NC}"
fi

python -c "import rich" 2>/dev/null && echo -e "${GREEN}✓ rich${NC}" || {
    echo -e "${YELLOW}⚠ rich saknas — installerar...${NC}"
    pip install rich -q
}
python -c "import nouse" 2>/dev/null && echo -e "${GREEN}✓ nouse${NC}" || {
    echo -e "${RED}✗ nouse ej installerat${NC}"
    echo -e "  ${YELLOW}Kör: pip install -e .${NC}"
    MISSING=1
}

if [[ $MISSING -eq 1 ]]; then
    echo -e "\n${RED}Avbryter — åtgärda saknade beroenden ovan.${NC}"
    exit 1
fi

echo ""

# ── Skapa output-katalog ──────────────────────────────────────────────────────
mkdir -p "$REPO_ROOT/IMG"

# ── Spela in med asciinema ────────────────────────────────────────────────────
echo -e "${BOLD}Spelar in terminal-session...${NC}"
echo -e "${CYAN}(88 kolumner × 40 rader — optimalt för GitHub README-GIF)${NC}"
echo ""

# Bygg inspelningskommando
#   --cols/--rows:   terminalstorlek
#   --overwrite:     skriv över befintlig inspelning
#   --quiet:         inga asciinema-meddelanden i terminalen
RECORD_CMD=(
    asciinema rec
    --cols 88
    --rows 40
    --overwrite
    --quiet
    --command "python $DEMO_SCRIPT"
    "$CAST_FILE"
)

"${RECORD_CMD[@]}"

if [[ ! -f "$CAST_FILE" ]]; then
    echo -e "${RED}✗ Inspelning misslyckades — $CAST_FILE skapades inte${NC}"
    exit 1
fi

CAST_SIZE=$(du -h "$CAST_FILE" | cut -f1)
echo -e "${GREEN}✓ Inspelning klar: $CAST_FILE ($CAST_SIZE)${NC}"
echo ""

# ── Konvertera till GIF ───────────────────────────────────────────────────────
if [[ "$AGG_CMD" == "agg" ]]; then
    echo -e "${BOLD}Konverterar till GIF med agg...${NC}"

    agg \
        --font-size 14 \
        --line-height 1.4 \
        --cols 88 \
        --rows 40 \
        --theme monokai \
        --speed 1.1 \
        "$CAST_FILE" \
        "$GIF_FILE"

    GIF_SIZE=$(du -h "$GIF_FILE" | cut -f1)
    echo -e "${GREEN}✓ GIF klar: $GIF_FILE ($GIF_SIZE)${NC}"

elif [[ "$AGG_CMD" == "docker" ]]; then
    echo -e "${BOLD}Konverterar till GIF via Docker...${NC}"

    docker run --rm \
        -v "$REPO_ROOT/IMG:/data" \
        ghcr.io/asciinema/agg:latest \
        --font-size 14 \
        --line-height 1.4 \
        --theme monokai \
        --speed 1.1 \
        /data/demo.cast \
        /data/demo.gif

    GIF_SIZE=$(du -h "$GIF_FILE" | cut -f1)
    echo -e "${GREEN}✓ GIF klar via Docker: $GIF_FILE ($GIF_SIZE)${NC}"

else
    echo -e "${YELLOW}⚠ Hoppar över GIF-konvertering (agg saknas)${NC}"
    echo -e "  ${CYAN}.cast-fil sparad: $CAST_FILE${NC}"
    echo -e "  ${CYAN}Alternativ:"
    echo -e "    1. Ladda upp till: asciinema upload $CAST_FILE"
    echo -e "    2. Installera agg och kör scriptet igen${NC}"
fi

# ── Sammanfattning ────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Klart!${NC}"
echo ""
[[ -f "$GIF_FILE" ]] && echo -e "  ${GREEN}GIF:   $GIF_FILE${NC}"
echo -e "  ${GREEN}Cast:  $CAST_FILE${NC}"
echo ""
echo -e "  ${BOLD}Lägg till i README.md:${NC}"
echo -e "  ${CYAN}<p align=\"center\">"
echo -e "    <img src=\"IMG/demo.gif\" alt=\"NoUse demo\" width=\"700\"/>"
echo -e "  </p>${NC}"
echo ""
echo -e "  ${BOLD}Ladda upp till asciinema.org:${NC}"
echo -e "  ${CYAN}asciinema upload $CAST_FILE${NC}"
echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════${NC}"
