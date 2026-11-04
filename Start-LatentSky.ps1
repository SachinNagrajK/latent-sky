Set-Location -LiteralPath $PSScriptRoot
$nodePath = (Get-Command node -ErrorAction SilentlyContinue).Source
if (-not $nodePath) { $nodePath = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' }
& $nodePath node_modules/vite/bin/vite.js --host 127.0.0.1
