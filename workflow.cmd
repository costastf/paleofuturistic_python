: ; unset VIRTUAL_ENV; exec uv run python _CI/lib/vendor/bin/invoke --search-root _CI "$@"
@set "VIRTUAL_ENV="
@uv run python _CI\lib\vendor\bin\invoke --search-root _CI %*
