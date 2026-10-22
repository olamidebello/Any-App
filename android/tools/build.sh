#!/bin/bash
# Dependency-light Android build: Java 17 and Android SDK 35 only.
set -euo pipefail
TASK_ROOT=$(cd "$(dirname "$0")/.." && pwd)
: "${ANDROID_HOME:?Set ANDROID_HOME to the Android SDK}"
TASK_TOOLS="$ANDROID_HOME/build-tools/35.0.0"
TASK_BUILD="$TASK_ROOT/app/build/manual"
TASK_OUTPUT="$TASK_ROOT/app/build/outputs/apk/debug"
mkdir -p "$TASK_BUILD/gen" "$TASK_BUILD/classes" "$TASK_BUILD/dex" "$TASK_OUTPUT"
python3 - "$TASK_ROOT" "$TASK_BUILD" <<'PY'
import os,sys,xml.etree.ElementTree as ET
from pathlib import Path
root=Path(sys.argv[1]);build=Path(sys.argv[2]);ns='http://schemas.android.com/apk/res/android'
ET.register_namespace('android',ns)
tree=ET.parse(root/'app/src/main/AndroidManifest.xml');manifest=tree.getroot();manifest.set('package','com.olamidepanel.anyapps.dev');manifest.set('{'+ns+'}versionCode',os.environ.get('APP_VERSION_CODE','1'));manifest.set('{'+ns+'}versionName','1.0.0-dev')
sdk=ET.Element('uses-sdk');sdk.set('{'+ns+'}minSdkVersion','26');sdk.set('{'+ns+'}targetSdkVersion','35');manifest.insert(0,sdk)
# The activity's Java namespace differs from the development application id.
manifest.find('application/activity').set('{'+ns+'}name','com.olamidepanel.anyapps.MainActivity')
manifest.find('application').set('{'+ns+'}debuggable','true')
tree.write(build/'AndroidManifest.xml',encoding='utf-8',xml_declaration=True)
PY
"$TASK_TOOLS/aapt" package -f -M "$TASK_BUILD/AndroidManifest.xml" -S "$TASK_ROOT/app/src/main/res" -I "$ANDROID_HOME/platforms/android-35/android.jar" -J "$TASK_BUILD/gen" -F "$TASK_BUILD/resources.apk"
find "$TASK_ROOT/app/src/main/java" "$TASK_BUILD/gen" -name '*.java' > "$TASK_BUILD/sources.txt"
if command -v javac >/dev/null 2>&1; then
  javac -source 8 -target 8 -bootclasspath "$ANDROID_HOME/platforms/android-35/android.jar" -d "$TASK_BUILD/classes" @"$TASK_BUILD/sources.txt"
else
  : "${ANYAPPS_ECJ_JAR:?Install a JDK or set ANYAPPS_ECJ_JAR to the Eclipse compiler JAR}"
  java -jar "$ANYAPPS_ECJ_JAR" -source 8 -target 8 -bootclasspath "$ANDROID_HOME/platforms/android-35/android.jar" -d "$TASK_BUILD/classes" @"$TASK_BUILD/sources.txt"
fi
python3 - "$TASK_BUILD" <<'PY'
import sys,zipfile
from pathlib import Path
b=Path(sys.argv[1])
with zipfile.ZipFile(b/'classes.jar','w',zipfile.ZIP_DEFLATED) as z:
 for f in (b/'classes').rglob('*.class'):z.write(f,f.relative_to(b/'classes'))
PY
"$TASK_TOOLS/d8" --min-api 26 --lib "$ANDROID_HOME/platforms/android-35/android.jar" --output "$TASK_BUILD/dex" "$TASK_BUILD/classes.jar"
cp "$TASK_BUILD/resources.apk" "$TASK_BUILD/unsigned.apk"
(cd "$TASK_BUILD/dex" && "$TASK_TOOLS/aapt" add "$TASK_BUILD/unsigned.apk" classes.dex)
"$TASK_TOOLS/zipalign" -f -p 4 "$TASK_BUILD/unsigned.apk" "$TASK_BUILD/aligned.apk"
TASK_KEY_DIR=${ANYAPPS_DEBUG_KEY_DIR:-"$HOME/.android"}
mkdir -p "$TASK_KEY_DIR"
if [[ ! -f "$TASK_KEY_DIR/anyapps-debug.keystore" ]]; then
  keytool -genkeypair -keystore "$TASK_KEY_DIR/anyapps-debug.keystore" -storepass android -keypass android -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 3650 -dname 'CN=AnyApps Development,O=AnyApps,C=US' >/dev/null 2>&1
  chmod 600 "$TASK_KEY_DIR/anyapps-debug.keystore"
fi
"$TASK_TOOLS/apksigner" sign --ks "$TASK_KEY_DIR/anyapps-debug.keystore" --ks-key-alias androiddebugkey --ks-pass pass:android --key-pass pass:android --out "$TASK_OUTPUT/app-debug.apk" "$TASK_BUILD/aligned.apk"
"$TASK_TOOLS/apksigner" verify --verbose "$TASK_OUTPUT/app-debug.apk"
"$TASK_TOOLS/aapt" dump badging "$TASK_OUTPUT/app-debug.apk" | sed -n '1p'
(cd "$TASK_OUTPUT" && sha256sum app-debug.apk > app-debug.apk.sha256)
printf 'Development APK built. Production signing is not configured.\n'
