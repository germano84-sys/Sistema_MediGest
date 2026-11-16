$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$environmentFile = Join-Path $repositoryRoot ".env"
$environment = @{}

if (Test-Path $environmentFile) {
    foreach ($line in Get-Content $environmentFile) {
        if ($line -match "^\s*([^#=]+?)\s*=(.*)$") {
            $environment[$matches[1].Trim()] = $matches[2].Trim().Trim('"').Trim("'")
        }
    }
}

$clientSecret = $environment["KEYCLOAK_ADMIN_CLIENT_SECRET"]
if (-not $clientSecret) {
    $clientSecret = "medigest-local-only-admin-client-secret"
}

function Invoke-KeycloakCli {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [switch]$WithClientSecret
    )

    $arguments = @("compose", "exec", "-T")
    if ($WithClientSecret) {
        $arguments += @("-e", "KEYCLOAK_ADMIN_CLIENT_SECRET=$clientSecret")
    }
    $arguments += @("keycloak", "sh", "-c", "cd /opt/keycloak/bin && $Command")
    & docker @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Keycloak service-client provisioning failed with exit code $LASTEXITCODE"
    }
}

Push-Location $repositoryRoot
try {
    Invoke-KeycloakCli './kcadm.sh config credentials --server http://localhost:8080 --realm master --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD"' | Out-Null

    $clientJson = Invoke-KeycloakCli "./kcadm.sh get clients -r medigest -q clientId=medigest-admin-api"
    $clients = ($clientJson -join "`n") | ConvertFrom-Json
    $client = @($clients) | Where-Object { $_.clientId -eq "medigest-admin-api" } | Select-Object -First 1
    $clientSettings = @(
        "-s clientId=medigest-admin-api",
        "-s enabled=true",
        "-s protocol=openid-connect",
        "-s publicClient=false",
        "-s serviceAccountsEnabled=true",
        "-s standardFlowEnabled=false",
        "-s directAccessGrantsEnabled=false",
        '-s secret="$KEYCLOAK_ADMIN_CLIENT_SECRET"'
    ) -join " "

    if ($client) {
        Invoke-KeycloakCli "./kcadm.sh update clients/$($client.id) -r medigest $clientSettings" -WithClientSecret
    } else {
        Invoke-KeycloakCli "./kcadm.sh create clients -r medigest $clientSettings" -WithClientSecret
    }

    Invoke-KeycloakCli "./kcadm.sh add-roles -r medigest --uusername service-account-medigest-admin-api --cclientid realm-management --rolename manage-users --rolename view-users"
} finally {
    Pop-Location
}

Write-Output "Keycloak admin API client is configured with limited user-management roles."
