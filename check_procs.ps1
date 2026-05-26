Get-Process python | ForEach-Object {
    $p = $_
    try {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)" -ErrorAction Stop | Select-Object -ExpandProperty CommandLine)
    } catch {
        $cmd = "N/A"
    }
    "$($p.Id): $cmd"
}