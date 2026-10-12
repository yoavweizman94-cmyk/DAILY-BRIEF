# משימה מתוזמנת ל-ingest/gto_pull.py — עסקאות מתואמות מקובץ ה-Excel החם של GTO.
#
# רצה במחשב שבו GTO ו-Excel פתוחים, כי רק שם הנתונים קיימים: כל חצי שעה
# בימים שני–שישי, 10:00–18:30. הסקריפט עצמו לא כותב כשאין שינוי, לא כותב
# בסוף שבוע או לפני 09:50, ומפעיל פריסה של האתר פעם אחת ביום — כש-GTO מסמן
# סיום מסחר. רצה רק כשהמשתמש מחובר (Excel ו-GTO הם של הסשן שלו), בלי חלון.
#
# **ושתי קריאות השלמה בערב, 21:00 ו-23:30.** הנתונים הסופיים נשארים ב-GTO עד
# יום המסחר הבא. ב-12/10/2026 GTO נפתח רק ב-13:00 והקריאות של הנעילה נפלו לשמירה,
# ורק קריאה ידנית ב-23:40 אספה 26 ניירות במקום 5. כש-GTO פתוח בערב, ההשלמה
# אוספת את היום בלי שמישהו יבקש; כשלא — הקריאה נופלת לשמירה ואינה כותבת דבר.
#
#   powershell -ExecutionPolicy Bypass -File scripts\gto_task.ps1           התקנה
#   powershell -ExecutionPolicy Bypass -File scripts\gto_task.ps1 -Remove   הסרה
#
# יומן: %LOCALAPPDATA%\TLV-TASE-View\gto_pull.log
param([switch]$Remove)

$Name = "TLV TASE View - GTO coordinated trades"
if ($Remove) {
  Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
  Write-Output "Removed: $Name"
  return
}

$Root = Split-Path -Parent $PSScriptRoot
$Python = (Get-Command python.exe -ErrorAction Stop).Source
# pythonw — אותו מפרש בלי חלון קונסולה שקופץ כל חצי שעה.
$Pythonw = Join-Path (Split-Path $Python) "pythonw.exe"
if (-not (Test-Path $Pythonw)) { $Pythonw = $Python }

$Script = Join-Path $Root "ingest\gto_pull.py"
$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument ('"' + $Script + '"') -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At "10:00"
$Trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "10:00" `
    -RepetitionInterval (New-TimeSpan -Minutes 30) `
    -RepetitionDuration (New-TimeSpan -Hours 8 -Minutes 30)).Repetition
$Days = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
$Evening = @(
  (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Days -At "21:00"),
  (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Days -At "23:30")
)
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $Name -Action $Action -Trigger (@($Trigger) + $Evening) -Settings $Settings `
    -Principal $Principal -Force `
    -Description "Reads the GTO coordinated-trades workbook and pushes it to the private content repo (ingest/gto_pull.py)." | Out-Null
Write-Output "Registered: $Name ($Pythonw)"
