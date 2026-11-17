@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "GTA6CLIPS_INTERNAL=%~dp0_internal"
set "GTA6CLIPS_AUTOCLIP=%~dp0autoclip_runtime"
if not exist "%~dp0GTA6Clips.exe" (
  echo ERRO: GTA6Clips.exe nao encontrado. Extraia o ZIP oficial completo.
  pause
  exit /b 2
)
if not exist "%GTA6CLIPS_INTERNAL%\pythonnet\runtime\Python.Runtime.dll" (
  echo ERRO: Python.Runtime.dll nao encontrada. Extraia o ZIP completo.
  pause
  exit /b 2
)
if not exist "%GTA6CLIPS_INTERNAL%\webview\lib\Microsoft.Web.WebView2.Core.dll" (
  echo ERRO: Microsoft.Web.WebView2.Core.dll nao encontrada. Extraia o ZIP completo.
  pause
  exit /b 2
)
echo.
echo REPARO GTA VI CLIPS - PYTHON.NET E WEBVIEW2
echo.
echo Confirme a origem do ZIP antes de prosseguir:
echo https://github.com/lulualcides-sys/GTA-6-clips/releases
echo.
echo A extracao do ZIP pode ter marcado varias bibliotecas como arquivos
echo baixados da internet. Isto provoca erro .NET 0x80131515.
echo.
echo O reparo remove Zone.Identifier somente das bibliotecas DLL/PYD
echo em _internal e autoclip_runtime e dos EXE do runtime AutoClip.
echo O modelo de IA Ollama nao e instalado por este reparo.
echo Nao altera System32, dados pessoais, videos, Windows Defender
echo nem SmartScreen. Execute somente no pacote oficial conferido.
echo.
REM O modo nao interativo e exclusivo dos testes de GitHub Actions.
if /I "%GITHUB_ACTIONS%"=="true" if /I "%GTA6CLIPS_REPAIR_ONLY%"=="1" goto repair
choice /c SN /n /m "Confirmar reparo das bibliotecas do Nexus? [S/N] "
if errorlevel 2 exit /b 3
:repair
powershell.exe -NoProfile -NonInteractive -Command "$ErrorActionPreference='Stop'; $roots=@($env:GTA6CLIPS_INTERNAL); if(Test-Path -LiteralPath $env:GTA6CLIPS_AUTOCLIP -PathType Container){ $roots += $env:GTA6CLIPS_AUTOCLIP }; $files=@(); foreach($base in $roots){$root=Get-Item -LiteralPath $base; if($root.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Pasta redirecionada; reparo recusado'}; $types=if($base -eq $env:GTA6CLIPS_AUTOCLIP){@('.dll','.pyd','.exe')}else{@('.dll','.pyd')}; $files+=@(Get-ChildItem -LiteralPath $root.FullName -Recurse -File -Force | Where-Object {$_.Extension -in $types}) }; if($files.Count -eq 0){throw 'Nenhuma biblioteca encontrada'}; foreach($file in $files){if($file.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Biblioteca redirecionada; reparo recusado'}; Unblock-File -LiteralPath $file.FullName -ErrorAction Stop}; Write-Output ('Bibliotecas conferidas: '+$files.Count)"
if errorlevel 1 (
  echo.
  echo O reparo falhou. Confira a origem do pacote e as permissoes.
  pause
  exit /b 4
)
echo.
echo Bibliotecas do Nexus conferidas. Abrindo aplicativo...
if /I "%GTA6CLIPS_REPAIR_ONLY%"=="1" exit /b 0
start "" "%~dp0GTA6Clips.exe"
exit /b 0
