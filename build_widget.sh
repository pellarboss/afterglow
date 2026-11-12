#!/usr/bin/env bash
# Builds and installs the Afterglow macOS widget ("Afterglow Widget.app").
#
# Needs: Xcode, and your Apple ID signed in to Xcode (Xcode > Settings > Accounts).
# A free personal team is enough for your own Mac.
#
#   ./build_widget.sh                          # finds your signing team automatically
#   AFTERGLOW_TEAM=ABCDE12345 ./build_widget.sh  # if you have more than one team
set -euo pipefail
cd "$(dirname "$0")"
HERE="$(pwd)"
WIDGET_DIR="$HERE/widget"
DEST="$HOME/Applications/Afterglow Widget.app"

step() { printf "\n==> %s\n" "$1"; }

# 1. Xcode -------------------------------------------------------------------
if ! xcodebuild -version >/dev/null 2>&1; then
  echo "Xcode is installed but the command-line tools point elsewhere. Run this, then try again:"
  echo "  sudo xcode-select -s /Applications/Xcode.app/Contents/Developer"
  exit 1
fi

# 2. XcodeGen (turns widget/project.yml into an Xcode project) ----------------
if ! command -v xcodegen >/dev/null 2>&1; then
  step "Installing XcodeGen with Homebrew"
  brew install xcodegen
fi

# 3. Signing team -------------------------------------------------------------
TEAM="${AFTERGLOW_TEAM:-}"
if [ -z "$TEAM" ]; then
  step "Finding your Apple developer team"
  TMPD="$(mktemp -d)"
  security find-certificate -a -c "Apple Development" -p > "$TMPD/all.pem" 2>/dev/null || true
  awk -v d="$TMPD" '/BEGIN CERTIFICATE/{n++} n{print > (d "/c" n ".pem")}' "$TMPD/all.pem"
  TEAMS=""
  for f in "$TMPD"/c*.pem; do
    [ -f "$f" ] || continue
    SUBJ="$(openssl x509 -noout -subject -in "$f" 2>/dev/null || true)"
    T="$(printf "%s" "$SUBJ" | grep -Eo 'OU ?= ?[A-Z0-9]{10}' | grep -Eo '[A-Z0-9]{10}$' | head -1 || true)"
    N="$(printf "%s" "$SUBJ" | grep -Eo '(^|[/, ])O ?= ?[^,/]+' | head -1 | sed -E 's/^[/, ]?O ?= ?//' || true)"
    [ -n "$T" ] && TEAMS="${TEAMS}${T}|${N}"$'\n'
  done
  rm -rf "$TMPD"
  TEAMS="$(printf "%s" "$TEAMS" | sed '/^$/d' | sort -u)"
  COUNT="$(printf "%s\n" "$TEAMS" | grep -c . || true)"
  if [ "$COUNT" = "0" ]; then
    echo "No Apple Development certificate found. In Xcode: Settings > Accounts > add your Apple ID,"
    echo "then select your team > Manage Certificates > + > Apple Development. Then run this again."
    exit 1
  elif [ "$COUNT" != "1" ]; then
    echo "You have more than one signing team:"
    printf "%s\n" "$TEAMS" | sed 's/|/   /'
    echo "Run again with the one to use, e.g.:  AFTERGLOW_TEAM=${TEAMS%%|*} ./build_widget.sh"
    exit 1
  fi
  TEAM="${TEAMS%%|*}"
  echo "Using team $TEAM (${TEAMS#*|})"
fi

USER_SLUG="$(printf "%s" "${USER:-me}" | tr -cd 'a-zA-Z0-9' | tr 'A-Z' 'a-z')"
PREFIX="${AFTERGLOW_BUNDLE_PREFIX:-com.${USER_SLUG}.afterglow}"
GROUP="${TEAM}.afterglow"

# 4. Generate and build -------------------------------------------------------
step "Building Afterglow Widget (first build takes a minute or two)"
cd "$WIDGET_DIR"
export AFTERGLOW_TEAM="$TEAM" AFTERGLOW_PREFIX="$PREFIX" AFTERGLOW_GROUP="$GROUP"
xcodegen generate --spec project.yml --quiet
if ! xcodebuild -project AfterglowWidget.xcodeproj -scheme AfterglowWidget -configuration Release \
    -derivedDataPath "$WIDGET_DIR/build" -allowProvisioningUpdates \
    DEVELOPMENT_TEAM="$TEAM" build > "$WIDGET_DIR/build.log" 2>&1; then
  echo "Build failed. The important lines:"
  grep -E "error:|BUILD FAILED|requires a provisioning profile|No Account|signing" "$WIDGET_DIR/build.log" | head -25 || true
  echo
  echo "Full log: widget/build.log  (send it to Claude if you're stuck)"
  exit 1
fi
cd "$HERE"

# 5. Install ------------------------------------------------------------------
step "Installing to ~/Applications"
BUILT="$WIDGET_DIR/build/Build/Products/Release/Afterglow Widget.app"
mkdir -p "$HOME/Applications"
pkill -x "Afterglow Widget" 2>/dev/null || true
rm -rf "$DEST"
cp -R "$BUILT" "$DEST"
LSREG=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
[ -x "$LSREG" ] && "$LSREG" -f "$DEST" >/dev/null 2>&1 || true
open -g -j "$DEST"  # registers the widget with macOS and creates its shared folder
sleep 2

# 6. Point the Afterglow menu bar app at the widget ---------------------------
step "Connecting the menu bar app"
[ -x "$HERE/.venv/bin/python" ] || ./start.sh setup
WAS_RUNNING=0
if pkill -f "hue_menubar.py" 2>/dev/null; then WAS_RUNNING=1; sleep 1; fi
"$HERE/.venv/bin/python" - "$GROUP" "$DEST" <<'PY'
import sys
import hue_homekit as core
cfg = core.load_config()
cfg["widget_group"], cfg["widget_app"] = sys.argv[1], sys.argv[2]
core.save_config(cfg)
PY
if [ -d "$HERE/Afterglow.app" ]; then
  open "$HERE/Afterglow.app"
elif [ "$WAS_RUNNING" = "1" ]; then
  echo "Restart Afterglow so it starts feeding the widget."
fi

cat <<EOF

Done. To add the widget: right-click your desktop > Edit Widgets,
search for "Afterglow", then click the small widget (or drag it where you want it).

If macOS asks whether Afterglow can access data from other apps, click Allow:
that's Afterglow writing the theme for the widget to read.
EOF
