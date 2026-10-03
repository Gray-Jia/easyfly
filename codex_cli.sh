#!/usr/bin/env bash

export HTTP_PROXY="http://127.0.0.1:7897"
export HTTPS_PROXY="https://127.0.0.1:7897"
export NO_PROXY="localhost,127.0.0.1,::1"
export CODEX_HOME="$HOME/.codex-cli"

codex "$@"


