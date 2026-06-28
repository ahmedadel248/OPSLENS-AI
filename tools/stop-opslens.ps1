param(
    [int]$Port = 8000
)

$connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue

if ($connections) {
    $connections | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
        Write-Host "Stopping process on port $Port: $_"
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }

    Write-Host "OpsLens stopped."
} else {
    Write-Host "No OpsLens process is using port $Port."
}
