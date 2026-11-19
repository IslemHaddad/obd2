[app]
title = OBD Pro
package.name = obdpro
package.domain = com.islemhaddad
source.dir = .
source.include_exts = py,png,json
source.exclude_dirs = p4a-recipes,bin,.buildozer
version = 1.0.0
requirements = python3,kivy==2.3.1,pyjnius,bleak,typing_extensions
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,ACCESS_NETWORK_STATE,BLUETOOTH,BLUETOOTH_ADMIN,BLUETOOTH_SCAN,BLUETOOTH_CONNECT,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION
android.api = 34
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.enable_androidx = True
p4a.branch = v2024.01.21
p4a.local_recipes = p4a-recipes

[buildozer]
log_level = 2
warn_on_root = 0
