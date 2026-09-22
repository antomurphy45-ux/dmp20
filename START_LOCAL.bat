@echo off
set CONSTRUCTION_CONTROL_DB=%~dp0data\construction_control.db
set CONSTRUCTION_CONTROL_UPLOADS=%~dp0data\uploads
if not exist "%~dp0data\uploads" mkdir "%~dp0data\uploads"
py app.py
