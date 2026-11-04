param(
    [Parameter(Mandatory, Position=0)]
    [ValidateSet('install', 'uninstall', 'run')]
    [string]$Command,
    [ValidatePattern('^(?:[01][0-9]|2[0-3]):[0-5][0-9]$')]
    [string]$At = '08:00'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$taskName = 'TripCrew-MorningBrief-' + $identity.User.Value
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

switch ($Command) {
    'install' {
        if ($task) { throw 'Morning brief task already exists; uninstall it before changing its time or checkout.' }
        foreach ($file in @('bin\morning-brief.cmd', 'relay\.venv\Scripts\python.exe', 'relay\relay.local.toml')) {
            if (-not (Test-Path -LiteralPath (Join-Path $repo $file) -PathType Leaf)) {
                throw "Missing $file; finish morning brief setup first."
            }
        }
        $launcher = Join-Path $repo 'bin\morning-brief.cmd'
        $action = New-ScheduledTaskAction -Execute $env:ComSpec -Argument ('/d /s /c ""{0}""' -f $launcher) -WorkingDirectory $repo
        $trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.Add([timespan]::ParseExact($At, 'hh\:mm', [cultureinfo]::InvariantCulture)))
        $principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Ask Planner and Budget for the TripCrew morning brief.' | Out-Null
        Write-Output "Installed $taskName daily at $At (local time), while logged on."
    }
    'uninstall' {
        if ($task) { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false }
        Write-Output "Removed $taskName (if installed)."
    }
    'run' {
        if (-not $task) { throw 'Morning brief task is not installed; install it first or run bin\morning-brief.cmd directly.' }
        Start-ScheduledTask -TaskName $taskName
        Write-Output "Triggered $taskName; inspect relay/.local/brief.log and the task LastTaskResult for completion."
    }
}
