@echo off
uv run --project "%~dp0..\tools" --directory "%~dp0..\tools" python -m tripcrew %*
exit /b %errorlevel%
