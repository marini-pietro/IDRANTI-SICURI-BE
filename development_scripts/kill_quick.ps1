# Port based solution could be an effective alternative, but it is not recommended because of the following reasons:
# - more generic targeting - other processes could be using the same ports - need for constant port map
# - does not kill processes if they started partially or crashed before binding to ports
# - does not handle non-port based scripts

# Define the script names to kill
$scriptsToKill = @("log_server", "auth_server", "api_server")

Write-Host "Checking for processes running scripts: $($scriptsToKill -join ', ')" -ForegroundColor White

# Get all Python processes
$pythonProcesses = Get-Process python -ErrorAction SilentlyContinue
$pythonProcesses += Get-Process python3 -ErrorAction SilentlyContinue
$pythonProcesses += Get-Process pythonw -ErrorAction SilentlyContinue

foreach ($script in $scriptsToKill) {
    $found = $false
    
    # Filter Python processes by command line containing the script name
    foreach ($pythonProc in $pythonProcesses) {
        try {
            # Get command line arguments using WMI
            $commandLine = (Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $($pythonProc.Id)").CommandLine
            
            if ($commandLine -and $commandLine.Contains($script)) {
                $found = $true
                try {
                    Stop-Process -Id $pythonProc.Id -Force -ErrorAction Stop
                    Write-Host "Successfully killed process: $script (PID: $($pythonProc.Id))" -ForegroundColor Green
                } catch {
                    Write-Host "Failed to kill process: $script (PID: $($pythonProc.Id))." -ForegroundColor Red
                }
            }
        } catch {
            # Silently continue if we can't get command line info
        }
    }
    
    if (-not $found) {
        Write-Host "No running process found with script: $script" -ForegroundColor Yellow
    }
}