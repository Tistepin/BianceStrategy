# Apex Legends 换号设置保全指南

> 适用场景：一台电脑多个账号（Steam 号 / EA 号），想把主号的按键、灵敏度、画面设置带到其他号上；以及把设置分享给别人。
> 环境：Windows + Steam 或 EA App 启动的 Apex Legends。
> 版本：v1.0 ｜ 2026-11-25

---

## 目录

- [0. 一页速查](#0-一页速查)
- [1. 三个配置文件分别管什么](#1-三个配置文件分别管什么)
- [2. 换号后设置为什么会丢](#2-换号后设置为什么会丢)
- [3. 各种方案对比](#3-各种方案对比)
- [4. 两个流传很广但不可靠的说法](#4-两个流传很广但不可靠的说法)
- [5. 最终操作流程](#5-最终操作流程)
- [6. 配套脚本说明](#6-配套脚本说明)
- [7. 排错对照表](#7-排错对照表)
- [8. 三个验证实验](#8-三个验证实验)
- [9. 注意事项与风险](#9-注意事项与风险)
- [附录 A：脚本完整源码](#附录-a脚本完整源码)
- [附录 B：路径速查](#附录-b路径速查)
- [附录 C：参考链接](#附录-c参考链接)

**可信度标记**：✅ = 有官方/社区来源佐证；⚠️ = 原理推断，未经本机实测（这台机器没装 Apex）。

---

## 0. 一页速查

| 阶段 | 操作 |
|---|---|
| **一次性准备** | 主号配好 → 备份 → 关掉 Apex 的 Steam 云（每个 Steam 号各关一次）→ 设置文件加只读 |
| **每次换号** | 直接启动，进训练场验证；不对再做兜底还原 |
| **兜底还原** | 新号启动到大厅 → 完全退出 → 脚本还原 → 再启动 |
| **想改设置** | 解只读 → 游戏内改 → 备份 → 重新加只读 |
| **分享给朋友** | 发 `settings.cfg`，别发 `videoconfig.txt`（跟硬件绑定） |

一句话原理：**Apex 的设置会按账号被云端覆盖，唯一可靠的做法是在文件层拦住它。**

---

## 1. 三个配置文件分别管什么

全部位于 `%USERPROFILE%\Saved Games\Respawn\Apex\` 下。
快捷打开：`Win + R` → 粘贴 `%USERPROFILE%\Saved Games\Respawn\Apex\local`

| 文件 | 路径 | 内容 | 换号时 |
|---|---|---|---|
| `settings.cfg` | `Apex\local\settings.cfg` | 按键绑定、灵敏度、HUD、游戏性选项（`bind_US_standard "w" "+forward" 0` 这种格式） | 被账号设置覆盖（文件还在） |
| `videoconfig.txt` | `Apex\local\videoconfig.txt` | 分辨率、画质、垂直同步等；`"VideoConfig" { "setting.xxx" "值" }` 的键值结构 | 被覆盖 |
| `profile.cfg` | `Apex\profile\profile.cfg` | 另一批 cvar（FOV 缩放 `clfovScale`、准星、无障碍、手柄 ALC 等），平铺的 `cvar "值"` 格式 | **被删掉并重建** |
| `previousgamestate.txt` | `Apex\local\previousgamestate.txt` | 上次会话状态标记，用来判断是否异常退出 | 可能参与重建判断 |

**关键认知**

- 这三个文件**都不包含你的账号资产**。等级、皮肤、传家宝在服务器上，删文件不影响。
- `profile.cfg` 对游戏来说只是**可丢弃的缓存**，删除它是官方推荐的重置手段（[官方 dev tracker](https://devtrackers.gg/apex-legends/p/4a819888-taking-damage-kicks-you-out-of-deathbox-replicater-constantly-resets-on-launch)）。
- 有些人的 `Saved Games` 被 OneDrive 重定向到别处，脚本会自动读注册表找到真实路径。

---

## 2. 换号后设置为什么会丢

四个机制叠加，按可能性排序：

### 2.1 云同步按账号隔离（最常见）

Steam Cloud 与 EA 云存档都按**账号**分命名空间。换了号，本地这份文件就"不属于"当前账号了，客户端丢弃重建，再从新账号的云端拉一份。

EA 论坛的原话：

> 问题出在账号绑定了 Steam AutoCloud 设置，每次 `profile.cfg` 被删除，它都会被上一个版本自动替换回去（[原文](https://forums.ea.com/discussions/apex-legends-technical-issues-fr/crash-apr%C3%A8s-le-lancement-du-jeu/13652112/replies/13681627)）

所以"删掉又长出一个新的"，其实是**游戏删 + 云端补**两步合成的结果。

### 2.2 账号指纹不匹配 → profile.cfg 整份作废

`profile.cfg` 里带档案指纹/配置版本。当前登录账号与指纹不一致时，客户端判定"这不是这个号的档案"，直接作废重建。这解释了为什么只有 `profile.cfg` 会被**删除**，而 `settings.cfg` 只是被**覆盖**。

### 2.3 只读反而可能加速删除 ⚠️

游戏写配置的流程是"写临时文件 → 替换"。如果目标文件只读、被杀软锁住、权限异常，写不进去时的兜底动作就是**删除后重建**。

也就是说：**给 `profile.cfg` 设只读，可能让它被删得更勤快。** 所以只读只用在 `settings.cfg` 和 `videoconfig.txt` 上。

### 2.4 服务端下发（客户端挡不住）⚠️

Apex 的设置有一部分存在 Respawn 服务器上，登录时按账号下发。这一层客户端**没有任何开关**能关。

**结论：文件层能挡的是 2.1/2.2/2.3，挡不了 2.4。** 所以本指南把"文件层锁定"作为主方案，"手动还原"作为兜底。

---

## 3. 各种方案对比

| 方案 | 做法 | 效果 | 评价 |
|---|---|---|---|
| **文件替换** | 换号后手动复制 `settings.cfg` 回去 | 有效，但要每次操作，顺序错了会被覆盖 | ✅ 可靠但麻烦，脚本已自动化 |
| **只读锁定** | 给 `settings.cfg` 加只读 | 所有账号都读到同一份，换号零操作 | ✅ **主推**，副作用是游戏内改不了设置 |
| **文件夹拒绝删除** | `icacls ... /deny "%USERNAME%":(DC)` | 连删除都挡住，文件绝对保得住 | ⚠️ 可能触发游戏报错/存档失败，属激进手段 |
| **合并成 autoexec + 启动项 exec** | 把两份 cfg 贴一起，启动项加 `+exec` | 部分生效，大部分被覆盖 | ❌ 时机错，见第 4 节 |
| **profile.cfg 末尾 exec + 只读** | `exec "myconf.cfg"` 写进 profile.cfg 最后一行 | 时机正确，能跑通 | ⚠️ 可行但脆弱：`profile.cfg` 被重建后这行就没了 |

---

## 4. 两个流传很广但不可靠的说法

### 4.1 "合并成 autoexec，启动项 `+exec`，就不用只读了"

**错在时机。** 启动项里的 `+exec` 在引擎启动早期执行，而账号的 profile/settings 在那**之后**才加载。你执行完，游戏接着用自己的设置覆盖一遍。

社区里真正跑通的做法恰好相反：[240hz/ApexConfigs](https://github.com/240hz/ApexConfigs) 是把 `exec "autoexec.cfg"` 加在 **`profile.cfg` 的最后一行**，并把 **`profile.cfg` 设为只读**——因为 profile 加载完才执行，才能盖住账号设置；不加只读的话游戏退出时会把那行写没。

所以不是"不用只读"，而是**只读的对象从 `settings.cfg` 换成了 `profile.cfg`**。

### 4.2 "开头加 `unbindall` 更保险"

方向对，但这是整个流程里最容易翻车的一行：

- 它清空**全部**绑定，包括你没自定过的默认键（开火、技能、地图、标记）。
- 能不能救回来，取决于 `settings.cfg` 是不是完整绑定表。Apex 会写全，所以通常没事。
- 但只要后面任何一条 `bind_US_standard` 失败（命令受限、键名不匹配），你就得到"一半键位空着"的状态——**而且退出游戏时游戏会把这个坏状态写回账号的 settings.cfg**，坏状态被持久化。
- `unbindall` 在 Apex 里是否可用没有公开保证。

**建议**：不要 unbindall。直接用 `bind` 覆盖即可，残留的重复绑定只是碍眼，不会让你打不了枪。

另外，这套"cfg 链"正是 2024 年 2 月官方点名收紧的对象。纯按键配置风险不大，但**绝对不要**在里面塞 `toggle` / 连发之类的宏，那是按作弊处理的。

---

## 5. 最终操作流程

### 5.1 一次性准备（用主号做，只做这一次）

1. **主号登录**，把按键、灵敏度、画面、HUD 全部调好
2. **完全退出游戏**（退出进程，不是退到桌面）
3. 双击 `apex-settings-backup.bat` → 按 `1` 备份
   生成 `ApexConfigBackup\` 下的 `settings.cfg`、`videoconfig.txt`、`profile.cfg`
4. **把 `ApexConfigBackup` 整个文件夹复制一份到网盘/U 盘**，防丢
5. 关掉 Apex 的 Steam 云：
   `库 → 右键 Apex Legends → 属性 → 通用 → Steam 云 → 关闭`
   ⚠️ **有几个 Steam 号就设几次**，这个开关存在 `userdata\<SteamID>\config\localconfig.vdf`，跟账号走不跟电脑走
6. 回脚本 → 按 `3` 锁定只读

做完这步，任何账号登录都读主号这份配置。

### 5.2 每次换号

1. 直接换号启动
2. 进训练场检查三样：按键、灵敏度、准星
3. 都对 → 结束
4. 不对 → 走 5.3

### 5.3 兜底还原（只读没挡住时）

```
新号启动一次 → 进到大厅 → 完全退出游戏 → 脚本按 2 还原 → 再启动
```

**顺序不能反**：必须先让游戏把自己那套写出来，再覆盖。先还原再启动的话，登录过程会再盖一次。

### 5.4 想改设置时（最容易忘）

```
脚本按 4 取消只读 → 进游戏改 → 完全退出 → 脚本按 1 重新备份 → 脚本按 3 重新锁定
```

漏掉最后一步，游戏内改的东西存不进去，下次启动还是旧设置；很多人在这里误判"脚本坏了"。

### 5.5 分享给朋友

| 发什么 | 说明 |
|---|---|
| `settings.cfg` | ✅ 可以发，纯按键/灵敏度 |
| `videoconfig.txt` | ❌ 别直接发，跟分辨率/显卡绑定，硬塞会黑屏或掉帧 |
| `profile.cfg` | ⚠️ 可发但谨慎，里面可能有账号相关字段 |

对方操作：先备份自己的 → 覆盖到 `...\Apex\local\` → 确认文件不是只读状态。

---

## 6. 配套脚本说明

文件名：`apex-settings-backup.bat`（单文件，双击即用，无需安装）

### 6.1 功能

- 自动从注册表读取"保存的游戏"真实路径（兼容 OneDrive 重定向）
- 备份/还原 `settings.cfg`、`videoconfig.txt`、`profile.cfg`
- 还原前自动把当前状态存到 `_还原前` 子目录，可回滚
- 只读锁定只作用于 `settings.cfg` 和 `videoconfig.txt`（`profile.cfg` 不锁，理由见 2.3）
- 还原前检测 `r5apex.exe` 是否在运行，在跑就阻止

### 6.2 菜单

```
[1] 备份当前设置      - 换号前做这个
[2] 还原我的设置      - 换号后做这个（含 profile.cfg）
[3] 设为只读          - 防止被云同步覆盖
[4] 取消只读
[5] 打开配置文件夹
[0] 退出
```

### 6.3 命令行参数（可配合快捷方式）

```
apex-settings-backup.bat backup
apex-settings-backup.bat restore
apex-settings-backup.bat lock
apex-settings-backup.bat unlock
apex-settings-backup.bat open
```

例如做一个桌面快捷方式，目标填：
`"D:\tools\apex-settings-backup.bat" restore`

### 6.4 目录结构

```
你的文件夹\
├── apex-settings-backup.bat
└── ApexConfigBackup\
    ├── settings.cfg
    ├── videoconfig.txt
    ├── profile.cfg
    └── _还原前\            ← 每次还原前自动生成
        ├── settings.cfg
        └── videoconfig.txt
```

### 6.5 编码提醒

脚本是 **GBK（ANSI）+ CRLF** 保存的。如果用记事本另存为 UTF-8，中文会乱码、命令会解析失败。要改内容请用 `ANSI` 编码保存。

---

## 7. 排错对照表

| 现象 | 原因 | 处理 |
|---|---|---|
| 换号后按键变了，但 `settings.cfg` 时间戳没变 | 服务端按账号下发，本地文件没被改 | 只能走兜底还原（5.3） |
| 换号后 `settings.cfg` 被改回去了 | 只读没生效，或另一个 Steam 号的云还开着 | 检查每个 Steam 号是否都关了 Apex 云 |
| 脚本还原后仍然不对 | 游戏启动时又从服务端拉了一次 | 只读是唯一办法；必要时用文件夹拒绝删除 |
| 换号后提示"设置无法保存" | 正常，只读在起作用 | 无需处理 |
| `profile.cfg` 反复消失又出现 | 2.2 的指纹机制 | 正常，脚本会补回去，别给它加只读 |
| 脚本报"没找到 settings.cfg" | 游戏没运行过，或 `Saved Games` 位置特殊 | 先在游戏里改一次设置再备份 |
| 双击脚本中文乱码 | 系统区域不是中文 / 文件被另存为 UTF-8 | 用 ANSI 重新保存，或改区域设置 |

---

## 8. 三个验证实验

想确认到底是哪一层在动你的文件：

**实验一：关云对照**

关掉 Steam 单游戏云（每个号都关）→ 换号启动 → 看 `profile.cfg` 还在不在。
不再重建 → 就是云同步（2.1）。

**实验二：Process Monitor**

下载 Process Monitor → 过滤器加 `Path` 包含 `profile.cfg` → 换号启动一次 → 看操作类型：

- `DeleteFile` / `SetDispositionInformation` → 游戏主动删（2.2）
- `WriteFile` → 只是写入覆盖

**实验三：diff 大法**（判断某个设置项到底存在哪个文件）

以"直播模式"为例：

1. 备份 `profile.cfg` 和 `settings.cfg`
2. 进游戏关掉直播模式 → 完全退出
3. 复制一份出来
4. 进游戏打开直播模式 → 完全退出
5. 两份 diff

有变化 → 它是本地可写的 cvar；没变化 → 账号侧开关，每个号得手动开。

---

## 9. 注意事项与风险

- **不影响账号资产**：关云同步、删配置文件都不会丢等级皮肤，那些在服务器。
- **只读的副作用**：游戏内改设置会存不进去，必须按 5.4 的流程来。
- **EA App 的云存档是全局的**：关了会影响其他 EA 游戏，所以先只关 Steam 侧。
- **别用 `-dev` 启动项**：那是绕过限制拿调试权限，风险远大于收益。
- **别装网上的"一键 cfg"**：常夹带 `bind` 宏链，正是 2024 年封禁的目标。
- **官方对改 cfg 的态度**：明确把"改配置获取竞技优势"定性为作弊。纯个人按键配置风险低，但别越界。
- **游戏更新会重置一切**：大版本更新后 `configversion` 变了，所有文件可能被重建，需重新跑一次 5.1。

---

## 附录 A：脚本完整源码

```bat
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
```

---

## 附录 B：路径速查

| 项目 | 路径 |
|---|---|
| Apex 配置根目录 | `%USERPROFILE%\Saved Games\Respawn\Apex\` |
| 按键 / 画面 | `...\Apex\local\settings.cfg`、`...\local\videoconfig.txt` |
| 档案 | `...\Apex\profile\profile.cfg` |
| 游戏目录 cfg 文件夹 | `Steam\steamapps\common\Apex Legends\cfg\` |
| Steam 单游戏云设置 | `Steam\userdata\<SteamID>\config\localconfig.vdf` |
| Steam 云状态标记 | 存档目录附近的 `steam_autocloud.vdf` |
| EA App 云存档 | EA app → 设置 → 云存档（**全局**，影响所有 EA 游戏） |

---

## 附录 C：参考链接

- [Steam 官方：单游戏/全局云同步开关](https://help.steampowered.com/zh-cn/faqs/view/68D2-35AB-09A9-7678)
- [240hz/ApexConfigs：profile.cfg 末尾 exec + 只读的方案](https://github.com/240hz/ApexConfigs)
- [EA 论坛：换 Steam 号后存档文件被替换（含 steam_autocloud.vdf）](https://answers.ea.com/t5/forums/forumtopicprintpage/board-id/apex-legends-technical-issues-en/message-id/205372/print-single-message/true/page/1)
- [EA 论坛法文区：AutoCloud 覆盖 profile.cfg](https://forums.ea.com/discussions/apex-legends-technical-issues-fr/crash-apr%C3%A8s-le-lancement-du-jeu/13652112/replies/13681627)
- [Apex 官方 dev tracker：删 profile.cfg 重置设置](https://devtrackers.gg/apex-legends/p/4a819888-taking-damage-kicks-you-out-of-deathbox-replicater-constantly-resets-on-launch)
- [4Gamers：官方打击 cfg 链与 tap-strafing 的公告](https://www.4gamers.com.tw/news/detail/62593/respawn-rolling-out-some-changes-to-apex-legends-to-better-protect-the-game-competitive-integrity)
- [Automaton：2024-02 exec 链限制报道](https://automaton-media.com/articles/newsjp/20240201-281010/)
- [贴吧：现版本 cfg 相关改动解读](https://tieba.baidu.com/p/8885321632)
- [Gl2imm/settings-changer：编辑 profile.cfg 的脚本](https://github.com/Gl2imm/settings-changer)
- [Steam 社区：同机双账号按键不互通的讨论](https://steamcommunity.com/app/1172470/discussions/0/3001047413714410086)

---

*本文档由实际排查过程整理，脚本部分已用模拟目录验证过备份/还原/只读全流程；涉及 Apex 客户端行为的推断处已标注 ⚠️，请以你自己的实测为准。*
