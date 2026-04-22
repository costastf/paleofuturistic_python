#!/bin/sh
: ; case "$1" in info.*) exec uv run --python ">=3.11" --no-project python _CI/info.py "$@";; esac
: ; exec uv run python _CI/lib/vendor/bin/invoke --search-root _CI "$@"
@echo %1 | findstr /B "info." >nul && (uv run --python ">=3.11" --no-project python _CI\info.py %* & exit /b)
@uv run python _CI\lib\vendor\bin\invoke --search-root _CI %*
