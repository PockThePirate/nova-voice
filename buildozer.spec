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
source.include_exts = py,png,jpg,kv,atlas,json,wav,mp3

# (str) Application versionning
version = 1.0.0

# (list) Application requirements
# comma separated e.g. requirements = sqlite3,kivy
requirements = python3,kivy,kivymd,vosk,websockets,pyjnius,android,openssl

# (str) Presplash of the application (loading screen)
#presplash.filename = %(source.dir)s/assets/presplash.png

# (str) Icon of the application
#icon.filename = %(source.dir)s/assets/icon.png

# (str) Supported orientation (landscape, sensorLandscape, portrait or all)
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) Permissions
android.permissions = RECORD_AUDIO,FOREGROUND_SERVICE,WAKE_LOCK,INTERNET,ACCESS_NETWORK_STATE

# (bool) Enable Android auto backup feature (Android API >=23)
android.allow_backup = True

# (str) Android arch to build for
android.archs = arm64-v8a, armeabi-v7a

# (str) Android minimum version
android.minapi = 24

# (str) Android target api version
android.api = 33

# (str) Android NDK version
android.ndk = 25b

# (bool) Skip update check for android sdk
#android.skip_update = False

# (str) Android entry point
android.entry_point = main

# (str) gradle version
android.gradle = 8.0

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1