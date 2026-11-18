#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export ANDROID_HOME="${ANDROID_HOME:-${ANDROID_SDK_ROOT:?Android SDK required}}"
sdkmanager="$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager"
avdmanager="$ANDROID_HOME/cmdline-tools/latest/bin/avdmanager"
python tools/prepare_platforms.py
python tools/bootstrap_android.py
"$sdkmanager" 'platforms;android-36' 'build-tools;36.0.0' 'emulator' 'system-images;android-35;google_apis;x86_64'
printf 'sdk.dir=%s\n' "$ANDROID_HOME" > Android/local.properties
chmod +x Android/gradlew
(cd Android && ./gradlew --no-daemon assembleDebug assembleAndroidTest testDebugUnitTest lintDebug --console=plain)

export ANDROID_AVD_HOME="$RUNNER_TEMP/storagelens-avd"
mkdir -p "$ANDROID_AVD_HOME" artifacts/verification/android-ci
"$avdmanager" create avd --force --name StorageLens_CI --package 'system-images;android-35;google_apis;x86_64' --device pixel_6 <<< 'no'
"$ANDROID_HOME/emulator/emulator" -avd StorageLens_CI -port 5554 -no-window -no-audio -no-boot-anim -no-snapshot -gpu swiftshader_indirect -cores 2 -memory 2048 > artifacts/verification/android-ci/emulator.log 2>&1 &
emulator_pid=$!
adb="$ANDROID_HOME/platform-tools/adb"
cleanup(){ "$adb" -s emulator-5554 emu kill >/dev/null 2>&1 || kill "$emulator_pid" 2>/dev/null || true; }
trap cleanup EXIT
timeout 300 "$adb" -s emulator-5554 wait-for-device
deadline=$((SECONDS+300))
while [[ "$(timeout 10 "$adb" -s emulator-5554 shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" != '1' ]]; do
    if (( SECONDS >= deadline )); then echo 'Android test emulator did not become ready.' >&2; exit 1; fi
    sleep 3
done
"$adb" -s emulator-5554 shell input keyevent 82
"$adb" -s emulator-5554 install -r Android/app/build/outputs/apk/debug/app-debug.apk
"$adb" -s emulator-5554 install -r Android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
"$adb" -s emulator-5554 shell am instrument -w -r com.portfolio.storagelens.preview.test/androidx.test.runner.AndroidJUnitRunner | tee artifacts/verification/android-ci/instrumentation.log
grep -Eq 'OK \([0-9]+ tests?\)' artifacts/verification/android-ci/instrumentation.log
"$adb" -s emulator-5554 pull /sdcard/Android/data/com.portfolio.storagelens.preview/files/verification/. artifacts/verification/android-ci/
python tools/ci_assets.py android
