@echo off
cd /d %~dp0
powershell -NoExit -Command "python app.py"