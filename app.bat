@echo off
REM Paths are relative to this .bat's own location (%~dp0) so it runs from any clone.
REM Query-time embedding is a single short string, so this runs fine on CPU with no
REM GPU setup. (GPU only speeds up the one-time corpus INGEST -- see the README
REM "GPU note (ingest only)" if you want to accelerate that step.)
set PYTHONIOENCODING=utf-8
"%~dp0.venv\Scripts\python.exe" "%~dp0app.py"
