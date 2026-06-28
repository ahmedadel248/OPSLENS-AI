param(
    [string]$Namespace = "",
    [string]$Node = "",
    [int]$Port = 8000,
    [switch]$NoBrowser
)

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Stop-Port {
    param([int]$Port)

    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue

    if ($connections) {
        $connections | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
    }
}

function Encode([string]$Value) {
    return [System.Uri]::EscapeDataString($Value)
}

Stop-Port -Port $Port

if (-not $Namespace) {
    $Namespace = kubectl config view --minify --output "jsonpath={..namespace}" 2>$null
}

if (-not $Namespace) {
    $Namespace = "default"
}

if (-not $Node) {
    $Node = kubectl get nodes -o jsonpath="{.items[0].metadata.name}" 2>$null
}

if (-not $Node) {
    $Node = "minikube"
}

$python = Join-Path $Root "venv\Scripts\python.exe"

$url = "http://127.0.0.1:$Port/?namespace=$(Encode $Namespace)&node=$(Encode $Node)#investigateView"

Write-Host ""
Write-Host "Starting OpsLens AI"
Write-Host "Namespace: $Namespace"
Write-Host "Node:      $Node"
Write-Host "URL:       $url"
Write-Host ""

$process = Start-Process `
    -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "src.api.main:app", "--host", "127.0.0.1", "--port", "$Port") `
    -WorkingDirectory $Root `
    -PassThru `
    -NoNewWindow

Start-Sleep -Seconds 2

if (-not $NoBrowser) {
    Start-Process $url
}

Write-Host "Press Q to stop OpsLens cleanly."

while (-not $process.HasExited) {
    if ([Console]::KeyAvailable) {
        $key = [Console]::ReadKey($true)
        if ($key.Key -eq "Q") {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            Stop-Port -Port $Port
            break
        }
    }

    Start-Sleep -Milliseconds 250
}

Stop-Port -Port $Port
Write-Host "OpsLens stopped."
