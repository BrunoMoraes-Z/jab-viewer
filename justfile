set shell := ["pwsh", "-NoLogo", "-NoProfile", "-Command"]

# Formatação do projeto com Blue via uv
format:
	uv run blue .

# Alias comum
alias fmt := format

# Compilação: delega para build.bat
build:
	$ErrorActionPreference = 'Stop'
	Start-Process -FilePath (Resolve-Path './build.bat').Path -Wait -NoNewWindow

# Alias de conveniência
alias compile := build
alias compilar := build
