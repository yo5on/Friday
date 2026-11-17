@echo off
rem Type "friday" anywhere: (re)starts Core and the hotspot through the FRIDAY wireless task.
schtasks /end /tn "FRIDAY wireless" >nul 2>&1
rem an old Core would keep port 8765 and the new one would fail to start
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object CommandLine -match 'friday_core' | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
schtasks /run /tn "FRIDAY wireless" >nul || (echo Could not start the FRIDAY wireless task. & exit /b 1)
echo FRIDAY is starting. Console: http://127.0.0.1:8765/
