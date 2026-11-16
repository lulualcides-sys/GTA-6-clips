@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "GTA6CLIPS_DLL=%~dp0_internal\pythonnet\runtime\Python.Runtime.dll"
if not exist "%GTA6CLIPS_DLL%" (
  echo ERRO: Python.Runtime.dll nao encontrada no pacote.
  echo Extraia todo o ZIP oficial, incluindo a pasta _internal.
  pause
  exit /b 2
)
echo.
echo REPARO GTA VI CLIPS - PYTHON.NET
echo.
echo Use somente para pacote baixado do repositorio oficial:
echo https://github.com/lulualcides-sys/GTA-6-clips/releases
echo.
echo Esta operacao remove a marca de arquivo baixado da internet
echo apenas de _internal\pythonnet\runtime\Python.Runtime.dll.
echo NAO desativa Windows Defender, SmartScreen ou politicas do sistema.
echo.
REM O modo sem interface abaixo existe apenas para o teste automatizado em CI.
if /I "%GITHUB_ACTIONS%"=="true" if /I "%GTA6CLIPS_REPAIR_ONLY%"=="1" goto repair
choice /c SN /n /m "Confirmar reparo desta DLL? [S/N] "
if errorlevel 2 exit /b 3
:repair
powershell.exe -NoProfile -NonInteractive -Command "Unblock-File -LiteralPath $env:GTA6CLIPS_DLL -ErrorAction Stop"
if errorlevel 1 (
  echo.
  echo Falha ao desbloquear a DLL. Confira a origem do pacote e as permissoes.
  pause
  exit /b 4
)
echo DLL reparada. Abrindo o aplicativo...
if /I "%GTA6CLIPS_REPAIR_ONLY%"=="1" exit /b 0
start "" "%~dp0GTA6Clips.exe"
exit /b 0
