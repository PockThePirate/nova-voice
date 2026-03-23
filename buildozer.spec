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
source.include_exts = py,png,jpg,kv,atlas,json

# (str) Application versionning
version = 1.0.0

# (list) Application requirements
requirements = python3,kivy,kivymd,vosk,websockets

# (str) Supported orientation (landscape, sensorLandscape, portrait or all)
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) Permissions
android.permissions = RECORD_AUDIO,FOREGROUND_SERVICE,WAKE_LOCK,INTERNET

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

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1