# משימה מתוזמנת ל-scripts/catchup.py, שמשלימה ריצות של צנרות המקור ש-GitHub לא הפעיל.
#
# ה-cron של GitHub מפיל את רוב הריצות. ב-12/11/2026, בין 18:00 ל-21:00, לא רצו
# הכותרות, ההשפעה על מניות והסחורות, והעמודים נשארו עם שעה ישנה.
# כל 15 דקות הסקריפט בודק לכל צנרת אם המשבצת האחרונה שלה כוסתה, ומשגר רק את
# מה שחסר. כשה-cron עובד, לא קורה דבר. את המהדורות עצמן מכסה ensure_task.ps1.
#
# המשימה רצה רק כשהמשתמש מחובר, כי האישור של GitHub שמור בחשבון שלו, והיא רצה
# בלי חלון (pythonw). כשהמחשב נדלק אחרי כיבוי (StartWhenAvailable), נשלחת ריצה
# אחת לכל צנרת שהחמיצה, ולא ריצה לכל משבצת.
#
#   powershell -ExecutionPolicy Bypass -File scripts\catchup_task.ps1           התקנה
#   powershell -ExecutionPolicy Bypass -File scripts\catchup_task.ps1 -Remove   הסרה
#
# יומן: %LOCALAPPDATA%\TLV-TASE-View\catchup.log
param([switch]$Remove)

$Name = "TLV TASE View - catch up pipelines"
if ($Remove) {
  Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
  Write-Output "Removed: $Name"
  return
}

$Root = Split-Path -Parent $PSScriptRoot
$Python = (Get-Command python.exe -ErrorAction Stop).Source
$Pythonw = Join-Path (Split-Path $Python) "pythonw.exe"
if (-not (Test-Path $Pythonw)) { $Pythonw = $Python }
$Script = Join-Path $Root "scripts\catchup.py"

$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument ('"' + $Script + '"') -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 15)
# שעון מקומי ולא רגע מוחלט. ראו את ההסבר ב-ensure_task.ps1 על סחיפת שעון החורף.
$Trigger.StartBoundary = ([datetime]$Trigger.StartBoundary).ToString("s")
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger -Settings $Settings `
    -Principal $Principal -Force `
    -Description "Every 15 minutes: dispatches each source pipeline whose GitHub cron slot passed without a run (scripts/catchup.py)." | Out-Null
Write-Output "Registered: $Name ($Pythonw)"
