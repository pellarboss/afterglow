#!/usr/bin/env bash
# Builds "Afterglow.app" (a menu bar app) in this folder.
# The app runs the code in this folder, so keep the folder where it is.
set -euo pipefail
cd "$(dirname "$0")"
HERE="$(pwd)"
APP_NAME="Afterglow"
APP="$HERE/$APP_NAME.app"

./start.sh setup

if ! command -v clang >/dev/null 2>&1; then
  echo "The Xcode Command Line Tools are needed to build the app. Install them with:"
  echo "  xcode-select --install"
  echo "Or skip the app and run it from Terminal:  ./start.sh menubar"
  exit 1
fi

echo "Building $APP_NAME.app ..."
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# Tiny native launcher, so macOS treats Afterglow as a real app
# (its own Bluetooth / network permissions, Open at Login, no Terminal).
cat > "$HERE/.launcher.c" <<'EOF'
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
extern char **environ;
static pid_t child = 0;
static void forward(int sig) { if (child > 0) kill(child, sig); }
int main(void) {
    setenv("AFTERGLOW_APP_PATH", APP_PATH, 1);
    char *args[] = { PYTHON, SCRIPT, NULL };
    signal(SIGTERM, forward);
    signal(SIGINT, forward);
    if (posix_spawn(&child, PYTHON, NULL, NULL, args, environ) != 0) {
        perror("Afterglow: could not start Python");
        return 1;
    }
    int status = 0;
    while (waitpid(child, &status, 0) < 0) {}
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}
EOF
clang -O2 -Wall \
  -DPYTHON="\"$HERE/.venv/bin/python\"" \
  -DSCRIPT="\"$HERE/hue_menubar.py\"" \
  -DAPP_PATH="\"$APP\"" \
  -o "$APP/Contents/MacOS/Afterglow" "$HERE/.launcher.c"
rm -f "$HERE/.launcher.c"

cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>$APP_NAME</string>
  <key>CFBundleDisplayName</key><string>$APP_NAME</string>
  <key>CFBundleIdentifier</key><string>local.afterglow.menubar</string>
  <key>CFBundleExecutable</key><string>Afterglow</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>LSUIElement</key><true/>
  <key>NSBluetoothAlwaysUsageDescription</key>
  <string>Afterglow connects to your Philips Hue light over Bluetooth.</string>
  <key>NSAppleEventsUsageDescription</key>
  <string>Afterglow reads the album cover playing in Spotify to match the light's colour.</string>
  <key>NSLocalNetworkUsageDescription</key>
  <string>Afterglow lets Apple Home on your iPhone control the light.</string>
  <key>NSBonjourServices</key>
  <array><string>_hap._tcp</string></array>
</dict>
</plist>
EOF

# App icon from the bulb artwork (optional; skipped if tools are missing).
if command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
  ICONSET="$HERE/.AppIcon.iconset"
  rm -rf "$ICONSET"; mkdir -p "$ICONSET"
  for s in 16 32 128 256 512; do
    sips -z $s $s icons/app_icon.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null 2>&1 || true
    d=$((s * 2))
    sips -z $d $d icons/app_icon.png --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null 2>&1 || true
  done
  iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns" 2>/dev/null || true
  rm -rf "$ICONSET"
fi

codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true

# The app used to be called "Hue Light": remove the old copy.
if [ -d "$HERE/Hue Light.app" ]; then
  rm -rf "$HERE/Hue Light.app"
  echo "Removed the old Hue Light.app"
fi

echo
echo "Built: $APP"
echo "Open it with:  open \"$APP\""
echo "(Keep this folder where it is; the app runs the code inside it.)"
