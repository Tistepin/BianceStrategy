@echo off
chcp 936 >nul
setlocal EnableExtensions EnableDelayedExpansion
title Apex 设置备份 / 还原

set "BAK=%~dp0ApexConfigBackup"
set "SG="

rem ---- 读取"保存的游戏"真实位置(可能被 OneDrive 重定向)----
for /f "tokens=2,*" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v "{4C5C32FF-BB9D-43B0-B5B4-2D72E54EAAA4}" 2^>nul') do set "SG=%%B"
if not defined SG set "SG=%USERPROFILE%\Saved Games"
call set "SG=%SG%"
set "CFG=%SG%\Respawn\Apex\local"
if defined APEXCFG set "CFG=%APEXCFG%"
for %%I in ("%CFG%\..\profile") do set "PROFDIR=%%~fI"

if /i "%~1"=="" goto menu
if /i "%~1"=="backup"  goto do_backup
if /i "%~1"=="restore" goto do_restore
if /i "%~1"=="lock"    goto do_lock
if /i "%~1"=="unlock"  goto do_unlock
if /i "%~1"=="open"    goto do_open
goto menu

:menu
cls
echo ============================================================
echo   Apex 设置备份 / 还原
echo ------------------------------------------------------------
echo   配置目录: %CFG%
if exist "%CFG%\settings.cfg" (echo   状态: 已找到 settings.cfg) else (echo   状态: 未找到 settings.cfg - 游戏还没运行过?)
if exist "%PROFDIR%\profile.cfg" (echo   档案文件: 有) else (echo   档案文件: 无 - 换号后会被重建, 属正常)
echo   备份目录: %BAK%
echo ============================================================
echo   [1] 备份当前设置 - 换号前做这个
echo   [2] 还原我的设置 - 换号后做这个 (含 profile.cfg)
echo   [3] 把设置文件设为只读 - 防止被云同步覆盖
echo   [4] 取消只读
echo   [5] 打开配置文件夹
echo   [0] 退出
echo ============================================================
set /p "CH=请输入数字并回车: "
if "%CH%"=="1" goto do_backup
if "%CH%"=="2" goto do_restore
if "%CH%"=="3" goto do_lock
if "%CH%"=="4" goto do_unlock
if "%CH%"=="5" goto do_open
if "%CH%"=="0" exit /b 0
goto menu

rem ================= 备份 =================
:do_backup
if not exist "%CFG%\settings.cfg" (
    echo.
    echo [失败] 没找到 %CFG%\settings.cfg
    echo        先启动一次 Apex 并改好设置, 再来备份。
    goto end_pause
)
if not exist "%BAK%" md "%BAK%" >nul 2>&1
copy /y "%CFG%\settings.cfg" "%BAK%\settings.cfg" >nul
if exist "%CFG%\videoconfig.txt" copy /y "%CFG%\videoconfig.txt" "%BAK%\videoconfig.txt" >nul
if exist "%PROFDIR%\profile.cfg" copy /y "%PROFDIR%\profile.cfg" "%BAK%\profile.cfg" >nul
echo.
echo [完成] 已备份到: %BAK%
dir /b "%BAK%"
goto end_pause

rem ================= 还原 =================
:do_restore
if not exist "%BAK%\settings.cfg" (
    echo.
    echo [失败] 备份目录里没有 settings.cfg, 先做一次备份。
    goto end_pause
)
tasklist /fi "imagename eq r5apex.exe" 2>nul | find /i "r5apex.exe" >nul
if not errorlevel 1 (
    echo.
    echo [注意] Apex 正在运行, 请先完全退出游戏再还原。
    goto end_pause
)
if not exist "%CFG%" md "%CFG%" >nul 2>&1
rem 先把当前设置另存一份, 避免还原错了没得救
if exist "%CFG%\settings.cfg" (
    if not exist "%BAK%\_还原前" md "%BAK%\_还原前" >nul 2>&1
    copy /y "%CFG%\settings.cfg" "%BAK%\_还原前\settings.cfg" >nul
    if exist "%CFG%\videoconfig.txt" copy /y "%CFG%\videoconfig.txt" "%BAK%\_还原前\videoconfig.txt" >nul
)
attrib -R "%CFG%\settings.cfg" >nul 2>&1
copy /y "%BAK%\settings.cfg" "%CFG%\settings.cfg" >nul
if exist "%BAK%\videoconfig.txt" (
    attrib -R "%CFG%\videoconfig.txt" >nul 2>&1
    copy /y "%BAK%\videoconfig.txt" "%CFG%\videoconfig.txt" >nul
)
rem profile.cfg: 换号时游戏会删掉重建, 所以这里直接补回去 (不设只读, 设了反而会被删)
if exist "%BAK%\profile.cfg" (
    if not exist "%PROFDIR%" md "%PROFDIR%" >nul 2>&1
    if not exist "%BAK%\_还原前" md "%BAK%\_还原前" >nul 2>&1
    if exist "%PROFDIR%\profile.cfg" copy /y "%PROFDIR%\profile.cfg" "%BAK%\_还原前\profile.cfg" >nul
    attrib -R "%PROFDIR%\profile.cfg" >nul 2>&1
    copy /y "%BAK%\profile.cfg" "%PROFDIR%\profile.cfg" >nul
)
echo.
echo [完成] 已还原到: %CFG%
echo        profile.cfg 已补到: %PROFDIR%
echo        原设置已存到: %BAK%\_还原前
echo        现在启动游戏, 进训练场确认一下按键和灵敏度。
goto end_pause

rem ================= 只读锁定 =================
:do_lock
if not exist "%CFG%\settings.cfg" (
    echo.
    echo [失败] 没找到 settings.cfg。
    goto end_pause
)
attrib +R "%CFG%\settings.cfg" >nul 2>&1
if exist "%CFG%\videoconfig.txt" attrib +R "%CFG%\videoconfig.txt" >nul 2>&1
echo.
echo [完成] 已设为只读, 云同步和游戏都改不动了。
echo        提醒1: 你自己在游戏里改设置也存不进去, 改之前先按 [4] 取消。
echo        提醒2: profile.cfg 不会被锁 - 锁了反而会被游戏删掉重建。
goto end_pause

:do_unlock
attrib -R "%CFG%\settings.cfg" >nul 2>&1
if exist "%CFG%\videoconfig.txt" attrib -R "%CFG%\videoconfig.txt" >nul 2>&1
echo.
echo [完成] 已取消只读。
goto end_pause

:do_open
if exist "%CFG%" (start "" "%CFG%") else (echo 目录不存在: %CFG%)
goto end_pause

:end_pause
echo.
pause
exit /b 0
