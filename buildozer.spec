[app]

# (str) Title of your application
title = Nova Voice

# (str) Package name
package.name = novavoice

# (str) Package domain (needed for android/ios packaging)
package.domain = org.openclaw

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include
source.include_exts = py,png,jpg,kv,atlas,json,mp3

# Include assets directory (vosk model)
android.add_assets = assets

# (list) Source files to exclude from release
source.exclude_exts = spec,pyc,md

# (str) Application version
version = 1.0.0

# (list) Application requirements
# Core: python3, kivy, kivymd
# Networking: websockets (for gateway connection)
# Audio: vosk (wake word), pyjnius (Android APIs)
# Crypto: pynacl (for Ed25519 device auth) - depends on libsodium
# Note: pynacl requires libsodium which has a p4a recipe
# Note: vosk requires bundled model in assets/
# IMPORTANT: Pin kivymd to 1.1.1 to avoid Cairo dependency (breaks Android)
# See: https://github.com/kivymd/KivyMD/issues/1842
requirements = python3,kivy==2.3.0,kivymd==1.1.1,websockets==12.0,pyjnius,vosk,pynacl,libsodium

# (str) Icon of the application
android.icon = icon.png

# (str) Supported orientation
orientation = portrait

# (bool) Fullscreen mode
fullscreen = 0

# (list) Permissions
android.permissions = RECORD_AUDIO,FOREGROUND_SERVICE,WAKE_LOCK,INTERNET

# (str) Android foreground service type (required for Android 14+)
android.foreground_service_type = mediaPlayback

# (bool) Enable Android auto backup
android.allow_backup = True

# (str) Android archs
android.archs = arm64-v8a, armeabi-v7a

# (str) Android minimum API
android.minapi = 24

# (str) Android API version (target Android 16 for S25 Ultra)
android.api = 36

# (str) Android NDK version
android.ndk = 27b

# (str) Android SDK path (GitHub Actions)
android.sdk_path = /usr/local/lib/android/sdk

# (str) Android entry point
android.entry_point = org.kivy.android.PythonActivity

# (str) Android theme
android.app_theme = @android:style/Theme.NoTitleBar

# (bool) Copy libraries
android.copy_libs = 1

# (str) Android logcat filter
android.logcat_filters = *:S python:D

# (bool) Debug mode
android.debuggable = 1

[buildozer]

# (int) Log level
log_level = 2

# (int) Warn on root
warn_on_root = 1