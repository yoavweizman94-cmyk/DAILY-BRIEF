# משימה מתוזמנת ל-scripts/ensure_editions.py — רשת ביטחון לתזמון של GitHub.
#
# ה-cron של GitHub מתאחר בשעות ולפעמים לא מגיע (04/10/2026: יום שלם בלי
# ברייף). המשימה הזו דוחפת בשעת כל מהדורה טריגר if_missing: הריצה מפיקה
# את המהדורה שבזמן אם היא חסרה, ויוצאת לפני האיסוף אם היא כבר נכתבה — כך
# שכשה-cron עבד, זה לא עולה דבר.
#
# השעות הן חמש דקות אחרי ה-cron, כדי לתת לו את ההזדמנות הראשונה:
#   06:50 בוקר (כל יום) · 15:05 צהריים (ב'–ה') · 18:05 נעילה (ב'–ה')
#   14:35 נעילה (ו') · 00:05 לילה (כל יום)
# מחשב כבוי בשעה הזו — המשימה רצה כשהוא נדלק (StartWhenAvailable), ואז
# הצנרת מפיקה את מה שבזמן באותו רגע.
#
# רצה כשהמשתמש מחובר — האישור של git שמור בחשבון שלו — ובלי חלון (pythonw).
#
#   powershell -ExecutionPolicy Bypass -File scripts\ensure_task.ps1           התקנה
#   powershell -ExecutionPolicy Bypass -File scripts\ensure_task.ps1 -Remove   הסרה
#
# יומן: %LOCALAPPDATA%\TLV-TASE-View\ensure_editions.log
param([switch]$Remove)
$Name = "TLV TASE View - ensure editions"
if ($Remove) {
  Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
  Write-Output "Removed: $Name"
  return
}
$Root = Split-Path -Parent $PSScriptRoot
$Python = (Get-Command python.exe -ErrorAction Stop).Source
$Pythonw = Join-Path (Split-Path $Python) "pythonw.exe"
if (-not (Test-Path $Pythonw)) { $Pythonw = $Python }
$Script = Join-Path $Root "scripts\ensure_editions.py"
$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument ('"' + $Script + '"') -WorkingDirectory $Root

$Weekdays = @("Monday", "Tuesday", "Wednesday", "Thursday")
$Triggers = @(
  (New-ScheduledTaskTrigger -Daily -At "06:50"),
  (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Weekdays -At "15:05"),
  (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Weekdays -At "18:05"),
  (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At "14:35"),
  (New-ScheduledTaskTrigger -Daily -At "00:05")
)
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Triggers -Settings $Settings `
    -Principal $Principal -Force `
    -Description "Pushes an if_missing trigger at each edition time, so an edition GitHub's cron delayed or dropped still gets written - once (scripts/ensure_editions.py)." | Out-Null
Write-Output "Registered: $Name ($Pythonw)"
