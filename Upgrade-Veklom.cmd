@echo off
setlocal EnableExtensions
title Veklom upgrade
rem Double-click to upgrade Genome Ledger, CAPPO and cAPI in the Veklom Docker Desktop stack.
rem It downloads the upgrade tools into %USERPROFILE%\veklom-upgrade\gnomledger with your Git
rem login, then runs scripts/veklom-upgrade.sh in WSL. The first step only reads and writes a
rem report; nothing changes until you answer y to a question.

echo Veklom stack upgrade: Genome Ledger, CAPPO, cAPI
echo.

where wsl >nul 2>&1 || (echo WSL is not installed. Docker Desktop uses it; install it with: wsl --install& goto :end)
where git >nul 2>&1 || (echo Git for Windows is needed: https://git-scm.com/download/win& goto :end)

set "TOOLS=%USERPROFILE%\veklom-upgrade\gnomledger"
if exist "%TOOLS%\.git" (
  echo Updating the upgrade tools in %TOOLS%
  git -C "%TOOLS%" config core.autocrlf false
  git -C "%TOOLS%" fetch -q origin main || goto :nogit
  git -C "%TOOLS%" checkout -q -f -B main origin/main || goto :nogit
) else (
  echo Downloading the upgrade tools to %TOOLS%
  git clone -q -c core.autocrlf=false https://github.com/reprewindai-dev/gnomledger.git "%TOOLS%" || goto :nogit
)

set "WTOOLS="
for /f "usebackq delims=" %%P in (`wsl -e wslpath -a "%TOOLS%"`) do set "WTOOLS=%%P"
if not defined WTOOLS (echo Could not start WSL. Open Docker Desktop, wait until it is running, then try again.& goto :end)

wsl -e bash "%WTOOLS%/scripts/veklom-upgrade.sh"
goto :end

:nogit
echo.
echo Could not download from GitHub. Sign in once with: git clone https://github.com/reprewindai-dev/gnomledger.git
echo in a terminal (Git asks for your GitHub login), then double-click this file again.

:end
echo.
pause
