# Define services
$services = @(
    @{ Name = "log_server"; Script = "..\log_server.py" },
    @{ Name = "auth_server"; Script = "..\auth_server.py" },
    @{ Name = "api_server"; Script = "..\api_server.py" }
)

foreach ($service in $services) {
    try {
        Write-Host "Starting $($service.Name)..." -ForegroundColor Cyan
        
        # Resolve full path
        $scriptPath = Resolve-Path $service.Script -ErrorAction Stop
        
        # Start process with unbuffered output (see output in IDE terminal instead of dedicated windows)
        # Warning: output will appears jumbled and hard to read because multiple services will be printing to the same terminal
        # using unbuffered output will aid to alleviate this problem, but for consistency and ease of debugging, it's recommended to use dedicated windows instead.
        # Uncomment the following lines to use unbuffered output in the current terminal:
        
        # $process = Start-Process python -ArgumentList "-u", $service.Script `
        #           -NoNewWindow

        # Start each process in a cmd window (visible)
        $process = Start-Process python -ArgumentList $service.Script `
                  -PassThru `
                  -WindowStyle Normal `
                  -NoNewWindow:$false
        
        Write-Host "$($service.Name) started (PID: $($process.Id))" -ForegroundColor Green
        Start-Sleep -Milliseconds 500  # Small delay between starts for better readability
        
    } catch {
        Write-Host "Failed to start $($service.Name): $_" -ForegroundColor Red
    }
}