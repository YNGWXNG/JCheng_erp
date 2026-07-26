[app]
title = JCheng_ERP
package.name = JCheng
package.domain = org.jiucheng
source.include_exts = py,png,jpg,json,kv,xml
version = 1.0
requirements = python3,kivy,flet,Pillow,requests,mysql-connector-python,numpy,reportlab
# If using opencv/pyzbar, add them here (but packaging native libs may be tricky)
# requirements = python3,kivy,flet,Pillow,requests,opencv-python,pyzbar,mysql-connector-python,numpy,reportlab

android.permissions = CAMERA,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
orientation = portrait
android.api = 31
android.minapi = 21
android.multidex = True

[buildozer]
log_level = 2
