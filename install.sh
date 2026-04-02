#!/usr/bin/env bash
# nouse install — kopplar systemd user-services och startar hjärnan
# Kör: bash install.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

echo "🧠 nouse install"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Synka dependencies
echo "→ uv sync..."
cd "$SCRIPT_DIR"
uv sync

# 2. Bygg Rust TDA-motorn
echo "→ Bygger Rust TDA-motor (persistent homology)..."
cd "$SCRIPT_DIR/crates/tda_engine"
"$SCRIPT_DIR/.venv/bin/maturin" develop --release 2>&1 | grep -E "(Finished|Installed|error)" || true
cd "$SCRIPT_DIR"
echo "  ✓ tda_engine"

# 2. Skapa systemd user-katalog
mkdir -p "$SYSTEMD_USER_DIR"

# 3. Kopiera service-filer
for f in \
  nouse-daemon.service \
  nouse-daemon.timer \
  nouse-backup.service \
  nouse-backup.timer \
  nouse-eval.service \
  nouse-eval.timer \
  nouse-watchdog.service \
  nouse-watchdog.timer; do
  if [[ ! -f "$SCRIPT_DIR/systemd/$f" ]]; then
    continue
  fi
  cp "$SCRIPT_DIR/systemd/$f" "$SYSTEMD_USER_DIR/$f"
  echo "  ✓ $f"
done

# 4. Ladda om systemd
systemctl --user daemon-reload

# 5. Aktivera och starta
systemctl --user enable --now nouse-daemon.timer
systemctl --user enable --now nouse-backup.timer
if [[ -f "$SYSTEMD_USER_DIR/nouse-watchdog.timer" ]]; then
  systemctl --user enable --now nouse-watchdog.timer
fi
if [[ -f "$SYSTEMD_USER_DIR/nouse-eval.timer" ]]; then
  systemctl --user enable --now nouse-eval.timer
fi

echo ""
echo "✅ nouse är installerat och körs i bakgrunden."
echo ""
echo "Kommandon:"
echo "  nouse daemon status        — se grafens nuläge"
echo "  nouse chat                 — prata med hjärnan"
echo "  nouse visualize            — öppna grafvisualiseringen"
echo "  journalctl --user -u nouse-daemon -f   — se brain-loop loggen live"
echo ""
echo "Systemd:"
echo "  systemctl --user status nouse-daemon"
echo "  systemctl --user status nouse-daemon.timer"
echo "  systemctl --user status nouse-eval.timer"
echo "  systemctl --user status nouse-watchdog.timer"
