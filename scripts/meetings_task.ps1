# משימה מתוזמנת ל-ingest/meetings_pull.py — תמלול הקלטות של שיחות עם חברות.
#
# **פעמיים ביום, ב-12:00 וב-17:30** — לבקשת יואב (28/10/2026). הבדיקה של 17:30
# מקדימה את הסקירות של הערב (Meetings ב-Actions, 19:30), כך שהקלטה של היום
# מסוכמת עוד באותו ערב. **בלי ריצת השלמה:** בדיקה שהוחמצה כי המחשב היה כבוי
# אינה רצה באיחור בערב, וההקלטה ממתינה לבדיקה הבאה.
#
# הסקריפט עצמו לא שולח דבר כשאין הקלטה חדשה, ורץ רק כשהמשתמש מחובר — התיקייה
# ב-OneDrive שלו, והאישור ל-GitHub שמור אצלו.
#
#   powershell -ExecutionPolicy Bypass -File scripts\meetings_task.ps1           התקנה
#   powershell -ExecutionPolicy Bypass -File scripts\meetings_task.ps1 -Remove   הסרה
#
# יומן: %LOCALAPPDATA%\TLV-TASE-View\meetings_pull.log
param([switch]$Remove)

$Name = "TLV TASE View - meeting recordings"
if ($Remove) {
  Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
  Write-Output "Removed: $Name"
  return
}

$Root = Split-Path -Parent $PSScriptRoot
$Python = (Get-Command python.exe -ErrorAction Stop).Source
# pythonw — אותו מפרש בלי חלון קונסולה שקופץ באמצע העבודה.
$Pythonw = Join-Path (Split-Path $Python) "pythonw.exe"
if (-not (Test-Path $Pythonw)) { $Pythonw = $Python }

$Script = Join-Path $Root "ingest\meetings_pull.py"
$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument ('"' + $Script + '"') -WorkingDirectory $Root
$Triggers = @(
  (New-ScheduledTaskTrigger -Daily -At "12:00"),
  (New-ScheduledTaskTrigger -Daily -At "17:30")
)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Triggers -Settings $Settings `
    -Principal $Principal -Force `
    -Description "Transcribes new meeting recordings with Soniox and pushes them to the private content repo (ingest/meetings_pull.py)." | Out-Null
Write-Output "Registered: $Name ($Pythonw)"
