param(
    [switch]$Detached
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Output "Created .env from .env.example. Review development credentials before use."
}

$composeArgs = @("up", "--build")
if ($Detached) {
    $composeArgs += "-d"
}

& docker compose @composeArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
