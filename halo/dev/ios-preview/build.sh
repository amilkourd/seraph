#!/bin/sh
# Builds the Halo preview app for the iOS Simulator (no Xcode project) and prints the .app path.
# Install and run:  xcrun simctl install booted <app>  &&  SIMCTL_CHILD_HALO_URL=<url> xcrun simctl launch booted fr.seraph.halo-preview
set -e
cd "$(dirname "$0")"
OUT="${1:-${TMPDIR:-/tmp}/halo-preview}"
APP="$OUT/Halo.app"
rm -rf "$APP" && mkdir -p "$APP"
xcrun -sdk iphonesimulator swiftc -target arm64-apple-ios17.0-simulator -O main.swift -o "$APP/HaloPreview"
cp Info.plist "$APP/Info.plist"
codesign --force --sign - "$APP" >/dev/null 2>&1
echo "$APP"
