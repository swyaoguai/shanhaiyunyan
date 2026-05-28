@echo off
setlocal
chcp 65001 >nul

echo Stopping processes listening on ports 5656-5959...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ports = 5656..5959; " ^
  "$listeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains [int]$_.LocalPort } | Sort-Object LocalPort, OwningProcess -Unique); " ^
  "if (-not $listeners.Count) { Write-Host 'No listening processes found on ports 5656-5959.'; exit 0 }; " ^
  "$targets = foreach ($item in $listeners) { $p = Get-Process -Id $item.OwningProcess -ErrorAction SilentlyContinue; [PSCustomObject]@{ Port = [int]$item.LocalPort; PID = [int]$item.OwningProcess; ProcessName = if ($p) { $p.ProcessName } else { '<unknown>' }; Path = if ($p) { $p.Path } else { '' } } }; " ^
  "Write-Host 'Processes to stop:'; $targets | Format-Table -AutoSize; " ^
  "$pids = @($targets | Select-Object -ExpandProperty PID -Unique | Where-Object { $_ -gt 0 -and $_ -ne $PID }); " ^
  "foreach ($processId in $pids) { $portsForProcess = @($targets | Where-Object { $_.PID -eq $processId } | Select-Object -ExpandProperty Port); $name = ($targets | Where-Object { $_.PID -eq $processId } | Select-Object -First 1 -ExpandProperty ProcessName); Stop-Process -Id $processId -Force -ErrorAction Stop; Write-Host ('Stopped PID {0} ({1}), ports {2}' -f $processId, $name, ($portsForProcess -join ', ')) }; " ^
  "Start-Sleep -Milliseconds 500; " ^
  "$remaining = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains [int]$_.LocalPort }); " ^
  "if ($remaining.Count) { Write-Warning 'Some ports are still occupied:'; $remaining | Select-Object LocalPort, OwningProcess | Format-Table -AutoSize; exit 1 }; " ^
  "Write-Host 'Ports 5656-5959 are free.'"

echo.
pause
