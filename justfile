set shell := ["pwsh", "-NoLogo", "-NoProfile", "-Command"]

format:
	uv run blue .

alias fmt := format

build:
	$ErrorActionPreference = 'Stop'
	Start-Process -FilePath (Resolve-Path './build.bat').Path -Wait -NoNewWindow

alias compile := build
alias compilar := build
