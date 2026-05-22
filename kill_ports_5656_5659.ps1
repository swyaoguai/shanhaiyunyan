[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [int[]]$Ports = @(5656, 5657, 5658, 5659)
)

$ErrorActionPreference = "Stop"

function Get-ListeningPortProcess {
    param([int[]]$TargetPorts)

    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        return Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $TargetPorts -contains [int]$_.LocalPort } |
            Select-Object @{Name = "Port"; Expression = { [int]$_.LocalPort } },
                          @{Name = "PID"; Expression = { [int]$_.OwningProcess } }
    }

    $connections = netstat -ano -p tcp |
        Select-String -Pattern "LISTENING" |
        ForEach-Object {
            $parts = ($_.Line.Trim() -split "\s+")
            if ($parts.Count -lt 5) { return }

            $localAddress = $parts[1]
            $pidValue = $parts[4]
            $portText = ($localAddress -split ":")[-1]
            $portValue = 0

            if ([int]::TryParse($portText, [ref]$portValue) -and $TargetPorts -contains $portValue) {
                [PSCustomObject]@{
                    Port = $portValue
                    PID = [int]$pidValue
                }
            }
        }

    return $connections
}

$listeners = @(Get-ListeningPortProcess -TargetPorts $Ports |
    Where-Object { $_.PID -gt 0 -and $_.PID -ne $PID } |
    Sort-Object Port, PID -Unique)

if (-not $listeners.Count) {
    Write-Host "No listening processes found on ports: $($Ports -join ', ')"
    exit 0
}

$targets = foreach ($listener in $listeners) {
    $process = Get-Process -Id $listener.PID -ErrorAction SilentlyContinue
    [PSCustomObject]@{
        Port = $listener.Port
        PID = $listener.PID
        ProcessName = if ($process) { $process.ProcessName } else { "<unknown>" }
        Path = if ($process) { $process.Path } else { "" }
    }
}

Write-Host "Processes listening on target ports:"
$targets | Format-Table -AutoSize

$pids = @($targets | Select-Object -ExpandProperty PID -Unique)
foreach ($processId in $pids) {
    $portsForProcess = @($targets | Where-Object { $_.PID -eq $processId } | Select-Object -ExpandProperty Port)
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    $name = if ($process) { $process.ProcessName } else { "<unknown>" }
    $targetDescription = "PID $processId ($name), ports $($portsForProcess -join ', ')"

    if ($PSCmdlet.ShouldProcess($targetDescription, "Stop-Process -Force")) {
        Stop-Process -Id $processId -Force -ErrorAction Stop
        Write-Host "Stopped $targetDescription"
    }
}

Start-Sleep -Milliseconds 500
$remaining = @(Get-ListeningPortProcess -TargetPorts $Ports |
    Where-Object { $_.PID -gt 0 -and $_.PID -ne $PID } |
    Sort-Object Port, PID -Unique)

if ($remaining.Count) {
    Write-Warning "Some target ports are still occupied:"
    $remaining | Format-Table -AutoSize
    exit 1
}

Write-Host "Ports are free: $($Ports -join ', ')"
