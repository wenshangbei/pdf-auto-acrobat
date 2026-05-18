@echo off
REM Kill all Adobe Acrobat related processes (cleanup stale state)
taskkill /F /IM Acrobat.exe       2>nul
taskkill /F /IM AcroCEF.exe       2>nul
taskkill /F /IM acrotray.exe      2>nul
taskkill /F /IM AdobeIPCBroker.exe 2>nul
taskkill /F /IM AdobeARM.exe      2>nul
taskkill /F /IM acrord32.exe      2>nul
taskkill /F /IM AcroBroker.exe    2>nul
echo Done.
timeout /t 2 >nul
