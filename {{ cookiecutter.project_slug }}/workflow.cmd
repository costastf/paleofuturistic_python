: ; case "$1" in info.*) exec python3 _CI/info.py "$@";; esac
: ; exec uv run python _CI/lib/vendor/bin/invoke --search-root _CI "$@"
@echo %1 | findstr /B "info." >nul && (python _CI\info.py %* & exit /b)
@uv run python _CI\lib\vendor\bin\invoke --search-root _CI %*
