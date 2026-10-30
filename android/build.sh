#!/usr/bin/env bash
# Builds Pokedex.apk without Gradle: aapt2 -> javac -> d8 -> zipalign -> apksigner (debug key).
# Needs a JDK 17+ and the Android SDK (build-tools 34+, platforms;android-34); GitHub's runners have both.
set -euo pipefail
cd "$(dirname "$0")"

SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
if [ -z "$SDK" ]; then
  for d in "$HOME/Library/Android/sdk" "$HOME/Android/Sdk" /usr/lib/android-sdk; do
    [ -d "$d/build-tools" ] && { SDK="$d"; break; }
  done
fi
[ -n "$SDK" ] && [ -d "$SDK/build-tools" ] || { echo "Android SDK not found: set ANDROID_HOME."; exit 1; }
BT="$SDK/build-tools/$(ls "$SDK/build-tools" | sort -V | tail -1)"
AJ="$(ls -d "$SDK"/platforms/android-*/android.jar | sort -V | tail -1)"

rm -rf out && mkdir -p out/gen out/classes out/assets
cp ../index.html out/assets/

"$BT/aapt2" compile --dir res -o out/res.zip
"$BT/aapt2" link -o out/base.apk -I "$AJ" --manifest AndroidManifest.xml --java out/gen out/res.zip \
  --min-sdk-version 26 --target-sdk-version 33 -A out/assets
javac --release 17 -cp "$AJ" -d out/classes $(find src out/gen -name '*.java')
"$BT/d8" --release --lib "$AJ" --output out $(find out/classes -name '*.class')
cp out/base.apk out/unaligned.apk
(cd out && zip -q unaligned.apk classes.dex)
"$BT/zipalign" -f 4 out/unaligned.apk out/aligned.apk

KEY=out/debug.keystore
keytool -genkeypair -keystore "$KEY" -storepass android -keypass android -alias hush -keyalg RSA -keysize 2048 \
  -validity 10000 -dname "CN=Hush" >/dev/null 2>&1
"$BT/apksigner" sign --ks "$KEY" --ks-pass pass:android --key-pass pass:android --out ../Pokedex.apk out/aligned.apk
echo "Built Pokedex.apk ($(du -k ../Pokedex.apk | cut -f1) KB)"
