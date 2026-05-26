$pid = 31772
try {
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$pid" -ErrorAction Stop | Select-Object -ExpandProperty CommandLine)
    Write-Host "PID $pid : $cmd"
} catch {
    Write-Host "PID $pid not found"
}

# Also check who owns port 8000
$proc = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object OwningProcess
Write-Host "Port 8000 owned by: $($proc.OwningProcess)"