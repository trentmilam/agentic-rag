@echo off
REM Quick verify: agentic-rag's fast, corpus-free checks as one pass/fail command.
REM Runs the pytest suite (unit tests + MCP tool wrappers + supersession cycle-safety);
REM no corpus needed. The corpus-dependent evals are the separate "Full verify" in the
REM README. Paths are relative to this .bat (%~dp0) so it runs from any clone.
set PYTHONIOENCODING=utf-8
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\verify.py"
