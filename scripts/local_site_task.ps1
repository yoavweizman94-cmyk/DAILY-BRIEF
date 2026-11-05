# משימה מתוזמנת וקיצור דרך לעותק המקומי של האתר (scripts/local_site.py).
#
# **המשימה מעדכנת את העותק כל חצי שעה**, כדי שקיצור הדרך ייפתח מיד: בנייה
# מלאה לוקחת דקה או שתיים, ובדיקה שלא מצאה שינוי לוקחת שניות. היא רצה רק
# כשהמשתמש מחובר, כי האישור ל-GitHub שמור אצלו.
#
# **קיצור הדרך** בשולחן העבודה מריץ את אותו סקריפט עם --open: הוא מושך את מה
# שחדש, בונה אם צריך ופותח את index.html בדפדפן. כשאין רשת נפתח העותק האחרון.
# הוא פותח חלון של python.exe ולא pythonw, כדי שיהיה ברור שהעדכון רץ.
#
#   powershell -ExecutionPolicy Bypass -File scripts\local_site_task.ps1           התקנה
#   powershell -ExecutionPolicy Bypass -File scripts\local_site_task.ps1 -Remove   הסרה
#
# יומן: %LOCALAPPDATA%\TLV-TASE-View\local_site.log
param([switch]$Remove)

$Name = "TLV TASE View - local site"
$Link = Join-Path ([Environment]::GetFolderPath("Desktop")) "TLV TASE View - עותק מקומי.lnk"
if ($Remove) {
  Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $Link -ErrorAction SilentlyContinue
  Write-Output "Removed: $Name and the desktop shortcut"
  return
}

$Root = Split-Path -Parent $PSScriptRoot
$Python = (Get-Command python.exe -ErrorAction Stop).Source
$Pythonw = Join-Path (Split-Path $Python) "pythonw.exe"
if (-not (Test-Path $Pythonw)) { $Pythonw = $Python }
$Script = Join-Path $Root "scripts\local_site.py"

$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument ('"' + $Script + '"') -WorkingDirectory $Root
# חזרה כל חצי שעה בלי משך מוגבל, מהיום.
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(5) -RepetitionInterval (New-TimeSpan -Minutes 30)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 45) -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger -Settings $Settings `
    -Principal $Principal -Force `
    -Description "Keeps a local HTML copy of the site up to date (scripts/local_site.py)." | Out-Null

$L = (New-Object -ComObject WScript.Shell).CreateShortcut($Link)
$L.TargetPath = $Python
$L.Arguments = '"' + $Script + '" --open'
$L.WorkingDirectory = $Root
$L.IconLocation = "$env:SystemRoot\System32\shell32.dll,13"
$L.Description = "Updates and opens the local copy of the site"
$L.Save()
Write-Output "Registered: $Name ($Pythonw)"
Write-Output "Shortcut: $Link"
