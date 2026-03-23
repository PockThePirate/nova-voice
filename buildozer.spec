[app]

# (str) Title of your application
title = Nova Voice

# (str) Package name
package.name = novavoice

# (str) Package domain (needed for android/ios packaging)
package.domain = org.openclaw

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas,json,mp3

# (list) Source files to exclude from release (at least one)
source.exclude_exts = spec,pyc,md

# (str) Application versionning
version = 1.0.0

# (list) Application requirements
# pyjnius>=1.5.0 for Python 3 compatibility
# cython<3.0 for compatibility with kivy/pyjnius
# edge-tts for TTS
requirements = python3,kivy,kivymd,vosk,websockets,pyjnius,edge-tts

# (str) Presplash of the application
#presplash.filename = %(source.dir)s/presplash.png

# (str) Icon of the application
android.icon = icon.png

# (str) Supported orientation (landscape, sensorLandscape, portrait or all)
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) Permissions
# RECORD_AUDIO - for wake word and speech recognition
# FOREGROUND_SERVICE - to keep running when screen is locked
# WAKE_LOCK - to prevent CPU sleep during listening
# INTERNET - for gateway connection
# RECORD_AUDIO for microphone access
android.permissions = RECORD_AUDIO,FOREGROUND_SERVICE,WAKE_LOCK,INTERNET,RECORD_AUDIO

# (bool) Enable Android auto backup feature (Android API >=23)
android.allow_backup = True

# (str) Android arch to build for
android.archs = arm64-v8a, armeabi-v7a

# (str) Android minimum API version
android.minapi = 24

# (str) Android API version to compile for (ndk version API level)
android.api = 33

# (str) Android NDK version
android.ndk = 25b

# (str) Android SDK path (force use system SDK)
android.sdk_path = /usr/local/lib/android/sdk

# (str) Android entry point
android.entry_point = org.kivy.android.PythonActivity

# (str) KivyMD theme
android.app_theme = @android:style/Theme.NoTitleBar

# (bool) Copy libraries instead of zipfile
android.copy_libs = 1

# (str) The Android logcat filter
android.logcat_filters = *:S python:D

# (bool) Enable Kivy debug mode
android.debuggable = 1

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1
