; ============================================================
; ov2n - VPN Client Installer
; Inno Setup Script
; 构建命令: ISCC.exe installer\ov2n_setup.iss
; 输出目录: dist\
; ============================================================

#define MyAppName      "ov2n"
; MyAppVersion can be overridden via /DMyAppVersion="x.y.z" on ISCC command line.
; The default here should match version.txt (single source of truth).
#ifndef MyAppVersion
  #define MyAppVersion   "1.4.2"
#endif
#define MyAppPublisher "Alfiy"
#define MyAppURL       "https://github.com/alfiy/pyQt_vpnv2ray_client"

; ── Launcher 改为 Python 脚本，不再使用 VBScript ──────────
; 快捷方式目标为 pythonw.exe（通过 {autopf} 定位），
; 参数为 ov2n_launcher.py，避免 wscript.exe 触发杀毒误报。
; 注意：MyAppExeName 仅用于卸载图标等极少数引用，
;       快捷方式 Filename/Parameters 单独指定，见 [Icons] 节。
#define MyAppExeName   "ov2n_launcher.py"
#define MyAppLauncher  "pythonw.exe"

; Python 安装包路径（相对于项目根目录）
#define PythonInstaller "resources\python\python-3.12.10-amd64.exe"

[Setup]
; ── 基本信息 ──────────────────────────────────────────────
AppId={{8F3A2E1D-4B6C-4D8E-9F0A-1B2C3D4E5F6A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
AppCopyright=Copyright (C) 2024 {#MyAppPublisher}

; ── 安装模式：让用户选择"仅为我"或"所有用户" ──────────────
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; ── 默认安装目录 ──────────────────────────────────────────
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes

; ── 输出 ──────────────────────────────────────────────────
OutputDir=..\dist
OutputBaseFilename=ov2n_{#MyAppVersion}_setup
SetupIconFile=..\resources\images\ov2n.ico
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=4

; ── 向导界面 ──────────────────────────────────────────────
WizardStyle=modern
ShowLanguageDialog=auto

; ── 最低系统要求 ──────────────────────────────────────────
MinVersion=10.0.17763
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

; ── 卸载 ──────────────────────────────────────────────────
Uninstallable=yes
UninstallDisplayName={#MyAppName} VPN Client
UninstallDisplayIcon={app}\resources\images\ov2n.ico
CreateUninstallRegKey=yes

; ── 其他 ──────────────────────────────────────────────────
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.bat
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ── 自定义消息 ────────────────────────────────────────────
[CustomMessages]
InstallPython=Python 3 is not installed. The installer will automatically install Python 3.12.10.
InstallingPython=Installing Python 3.12.10, please wait...
InstallingTAP=Installing TAP-Windows driver, please wait...
InstallingDeps=Installing Python dependencies (PyQt5, etc.), please wait...
TAPInstalled=TAP-Windows driver installed successfully.
AutoStartup=Start {#MyAppName} automatically at login
InstallForAllUsers=Install for all users (requires Administrator)
UninstallKeepData=Would you like to keep your configuration files?%n%n(Includes VPN config, Xray config, etc.)%n%nClick "Yes" to keep, "No" to delete all data.
UninstallStopService=Stopping OV2NService...

[Files]
; ── 应用程序核心文件 ─────────────────────────────────────
Source: "..\main.py";                     DestDir: "{app}";           Flags: ignoreversion
Source: "..\requirements.txt";            DestDir: "{app}";           Flags: ignoreversion
Source: "..\version.txt";                 DestDir: "{app}";           Flags: ignoreversion skipifsourcedoesntexist
Source: "..\ov2n.bat";                    DestDir: "{app}";           Flags: ignoreversion skipifsourcedoesntexist
; ── ov2n_launcher.py 替代原来的 ov2n_launcher.vbs ─────────
; 由 build_installer.bat 从 installer\src\ 复制到项目根目录后打包
Source: "..\ov2n_launcher.py";            DestDir: "{app}";           Flags: ignoreversion
; ov2n_launcher.vbs 已废弃，不再打包
Source: "..\ov2n.ps1";                    DestDir: "{app}";           Flags: ignoreversion skipifsourcedoesntexist

; ── Python 源码目录 ──────────────────────────────────────
Source: "..\core\*";                      DestDir: "{app}\core";      Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\ui\*";                        DestDir: "{app}\ui";        Flags: ignoreversion recursesubdirs createallsubdirs

; ── 图标资源 ─────────────────────────────────────────────
Source: "..\resources\images\*";          DestDir: "{app}\resources\images"; Flags: ignoreversion recursesubdirs createallsubdirs

; ── Xray 资源 ─────────────────────────────────────────────
Source: "..\resources\xray\*";            DestDir: "{app}\resources\xray";   Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

; ── OpenVPN 资源 ──────────────────────────────────────────
Source: "..\resources\openvpn\*";         DestDir: "{app}\resources\openvpn"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

; ── NSSM ─────────────────────────────────────────────────
Source: "..\resources\nssm\*";            DestDir: "{app}\resources\nssm";   Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

; ── TAP-Windows 驱动
; 解压到 {tmp}，安装完成后自动清理，不保留在安装目录
Source: "..\resources\tap-windows\tap-windows-installer.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall skipifsourcedoesntexist

; ── Python 安装包
; 解压到 {tmp}，安装完成后自动清理，不保留在安装目录
Source: "..\{#PythonInstaller}";          DestDir: "{tmp}";           Flags: deleteafterinstall skipifsourcedoesntexist

; ── Windows 脚本 ──────────────────────────────────────────
Source: "..\scripts\windows\*";           DestDir: "{app}\scripts\windows";  Flags: ignoreversion recursesubdirs createallsubdirs

; ── 日志目录占位 ─────────────────────────────────────────
Source: "..\logs\README.txt";             DestDir: "{app}\logs";      Flags: ignoreversion skipifsourcedoesntexist
Source: "..\service\README.md";           DestDir: "{app}\service";   Flags: ignoreversion skipifsourcedoesntexist

; ── 文档 ─────────────────────────────────────────────────
Source: "..\README.md";                   DestDir: "{app}";           Flags: ignoreversion skipifsourcedoesntexist
Source: "..\INSTALL.md";                  DestDir: "{app}";           Flags: ignoreversion skipifsourcedoesntexist

; ============================================================
; 创建的目录（确保空目录也存在）
; ============================================================
[Dirs]
Name: "{app}\logs"
Name: "{app}\core\openvpn"
Name: "{app}\core\xray"

; ============================================================
; 快捷方式
; Filename -> pythonw.exe (no wscript.exe, no antivirus false positive)
; Parameters -> ov2n_launcher.py
; GetPythonWPath() is defined in [Code], reads pythonw.exe path from registry
; ============================================================

[Icons]
; 开始菜单 - Filename 指向 pythonw.exe，Parameters 传入 .py 路径，避免经过 wscript.exe
Name: "{group}\{#MyAppName} VPN Client"; Filename: "{code:GetPythonWPath}"; Parameters: """{app}\ov2n_launcher.py"""; WorkingDir: "{app}"; IconFilename: "{app}\resources\images\ov2n.ico"; Comment: "ov2n - OpenVPN + Xray VPN Client"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"

; 桌面快捷方式（可选）
Name: "{autodesktop}\{#MyAppName} VPN Client"; Filename: "{code:GetPythonWPath}"; Parameters: """{app}\ov2n_launcher.py"""; WorkingDir: "{app}"; IconFilename: "{app}\resources\images\ov2n.ico"; Tasks: desktopicon

; 开机自启（可选）
Name: "{userstartup}\{#MyAppName} VPN Client"; Filename: "{code:GetPythonWPath}"; Parameters: """{app}\ov2n_launcher.py"""; WorkingDir: "{app}"; IconFilename: "{app}\resources\images\ov2n.ico"; Tasks: startup

; ============================================================
; 可选任务（在向导中显示勾选框）
; ============================================================
[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}";          GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startup";     Description: "{cm:AutoStartup}";                GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

; ============================================================
; 注册表
; ============================================================
[Registry]
Root: HKCU; Subkey: "Software\ov2n"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\ov2n"; ValueType: string; ValueName: "Version";    ValueData: "{#MyAppVersion}"

; ============================================================
; 安装步骤（Pascal 脚本）
; ============================================================
[Code]

// ── 全局变量 ─────────────────────────────────────────────
var
  PythonInstalled: Boolean;
  TAPInstalled:    Boolean;

// ── 检测 Python 是否已安装 ───────────────────────────────
function IsPythonInstalled(): Boolean;
var
  PythonPath: String;
  ResultCode: Integer;
begin
  Result := False;
  if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.12\InstallPath', '', PythonPath) then begin Result := True; Exit; end;
  if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.11\InstallPath', '', PythonPath) then begin Result := True; Exit; end;
  if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.10\InstallPath', '', PythonPath) then begin Result := True; Exit; end;
  if RegQueryStringValue(HKCU, 'SOFTWARE\Python\PythonCore\3.12\InstallPath', '', PythonPath) then begin Result := True; Exit; end;
  if RegQueryStringValue(HKCU, 'SOFTWARE\Python\PythonCore\3.11\InstallPath', '', PythonPath) then begin Result := True; Exit; end;
  if RegQueryStringValue(HKCU, 'SOFTWARE\Python\PythonCore\3.10\InstallPath', '', PythonPath) then begin Result := True; Exit; end;
  if Exec('python', '--version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    if ResultCode = 0 then begin Result := True; Exit; end;
end;

// ── 检测 TAP 驱动是否已安装 ──────────────────────────────
function IsTAPInstalled(): Boolean;
var
  TAPVersion: String;
begin
  Result := False;
  if RegQueryStringValue(HKLM, 'SOFTWARE\TAP-Windows',  'Version', TAPVersion) then begin Result := True; Exit; end;
  if RegQueryStringValue(HKLM, 'SOFTWARE\TAP-Windows6', 'Version', TAPVersion) then begin Result := True; Exit; end;
  if RegQueryStringValue(HKLM, 'SOFTWARE\OpenVPN\TapAdapter', '', TAPVersion)  then begin Result := True; Exit; end;
end;

// ── 从注册表读取 python.exe 完整路径 ─────────────────────
// 用于 pip 安装依赖，不依赖当前进程 PATH
function GetPythonExePath(): String;
var
  InstallPath: String;
begin
  Result := 'python'; // 兜底
  if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.12\InstallPath', '', InstallPath) then begin
    if FileExists(InstallPath + 'python.exe')  then begin Result := InstallPath + 'python.exe';  Exit; end;
    if FileExists(InstallPath + '\python.exe') then begin Result := InstallPath + '\python.exe'; Exit; end;
  end;
  if RegQueryStringValue(HKCU, 'SOFTWARE\Python\PythonCore\3.12\InstallPath', '', InstallPath) then begin
    if FileExists(InstallPath + 'python.exe')  then begin Result := InstallPath + 'python.exe';  Exit; end;
    if FileExists(InstallPath + '\python.exe') then begin Result := InstallPath + '\python.exe'; Exit; end;
  end;
  if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.11\InstallPath', '', InstallPath) then begin
    if FileExists(InstallPath + 'python.exe')  then begin Result := InstallPath + 'python.exe';  Exit; end;
    if FileExists(InstallPath + '\python.exe') then begin Result := InstallPath + '\python.exe'; Exit; end;
  end;
  if RegQueryStringValue(HKCU, 'SOFTWARE\Python\PythonCore\3.11\InstallPath', '', InstallPath) then begin
    if FileExists(InstallPath + 'python.exe')  then begin Result := InstallPath + 'python.exe';  Exit; end;
    if FileExists(InstallPath + '\python.exe') then begin Result := InstallPath + '\python.exe'; Exit; end;
  end;
  if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.10\InstallPath', '', InstallPath) then begin
    if FileExists(InstallPath + 'python.exe')  then begin Result := InstallPath + 'python.exe';  Exit; end;
    if FileExists(InstallPath + '\python.exe') then begin Result := InstallPath + '\python.exe'; Exit; end;
  end;
  if RegQueryStringValue(HKCU, 'SOFTWARE\Python\PythonCore\3.10\InstallPath', '', InstallPath) then begin
    if FileExists(InstallPath + 'python.exe')  then begin Result := InstallPath + 'python.exe';  Exit; end;
    if FileExists(InstallPath + '\python.exe') then begin Result := InstallPath + '\python.exe'; Exit; end;
  end;
end;

// ── 从注册表读取 pythonw.exe 完整路径 ────────────────────
// 供 [Icons] 节的 {code:GetPythonWPath} 调用，
// 快捷方式 Filename 指向 pythonw.exe 而非 wscript.exe，
// 从而避免杀毒软件对 wscript.exe + .vbs 组合的误报。
// Param 参数为 Inno Setup 回调约定，固定传空字符串，忽略即可。
function GetPythonWPath(Param: String): String;
var
  InstallPath: String;
begin
  Result := 'pythonw.exe'; // 兜底：依赖 PATH
  if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.12\InstallPath', '', InstallPath) then begin
    if FileExists(InstallPath + 'pythonw.exe')  then begin Result := InstallPath + 'pythonw.exe';  Exit; end;
    if FileExists(InstallPath + '\pythonw.exe') then begin Result := InstallPath + '\pythonw.exe'; Exit; end;
  end;
  if RegQueryStringValue(HKCU, 'SOFTWARE\Python\PythonCore\3.12\InstallPath', '', InstallPath) then begin
    if FileExists(InstallPath + 'pythonw.exe')  then begin Result := InstallPath + 'pythonw.exe';  Exit; end;
    if FileExists(InstallPath + '\pythonw.exe') then begin Result := InstallPath + '\pythonw.exe'; Exit; end;
  end;
  if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.11\InstallPath', '', InstallPath) then begin
    if FileExists(InstallPath + 'pythonw.exe')  then begin Result := InstallPath + 'pythonw.exe';  Exit; end;
    if FileExists(InstallPath + '\pythonw.exe') then begin Result := InstallPath + '\pythonw.exe'; Exit; end;
  end;
  if RegQueryStringValue(HKCU, 'SOFTWARE\Python\PythonCore\3.11\InstallPath', '', InstallPath) then begin
    if FileExists(InstallPath + 'pythonw.exe')  then begin Result := InstallPath + 'pythonw.exe';  Exit; end;
    if FileExists(InstallPath + '\pythonw.exe') then begin Result := InstallPath + '\pythonw.exe'; Exit; end;
  end;
  if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.10\InstallPath', '', InstallPath) then begin
    if FileExists(InstallPath + 'pythonw.exe')  then begin Result := InstallPath + 'pythonw.exe';  Exit; end;
    if FileExists(InstallPath + '\pythonw.exe') then begin Result := InstallPath + '\pythonw.exe'; Exit; end;
  end;
  if RegQueryStringValue(HKCU, 'SOFTWARE\Python\PythonCore\3.10\InstallPath', '', InstallPath) then begin
    if FileExists(InstallPath + 'pythonw.exe')  then begin Result := InstallPath + 'pythonw.exe';  Exit; end;
    if FileExists(InstallPath + '\pythonw.exe') then begin Result := InstallPath + '\pythonw.exe'; Exit; end;
  end;
end;

// ── 安装向导初始化 ────────────────────────────────────────
procedure InitializeWizard();
begin
  PythonInstalled := IsPythonInstalled();
  TAPInstalled    := IsTAPInstalled();
end;

// ── 安装步骤执行 ─────────────────────────────────────────
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  TmpDir:     String;
  AppDir:     String;
  PythonExe:  String;
  TAPExe:     String;
begin
  if CurStep = ssPostInstall then
  begin
    TmpDir := ExpandConstant('{tmp}');
    AppDir := ExpandConstant('{app}');

    ForceDirectories(AppDir + '\logs');

    // ── Step 1: 安装 Python ───────────────────────────────
    if not PythonInstalled then
    begin
      PythonExe := TmpDir + '\python-3.12.10-amd64.exe';
      if FileExists(PythonExe) then
      begin
        WizardForm.StatusLabel.Caption := ExpandConstant('{cm:InstallingPython}');
        if IsAdminInstallMode() then
          Exec(PythonExe,
            '/quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_pip=1',
            '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
        else
          Exec(PythonExe,
            '/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1',
            '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

        if ResultCode <> 0 then
          MsgBox(
            'Python 3.12 installation failed (exit code: ' + IntToStr(ResultCode) + ').' + #13#10 +
            'Please install Python 3.12 manually from https://www.python.org/' + #13#10 +
            'then run:  pip install -r "' + AppDir + '\requirements.txt"',
            mbError, MB_OK);
      end else
        MsgBox(
          'Python installer not found inside the package.' + #13#10 +
          'Expected path: ' + PythonExe + #13#10 +
          'Please install Python 3.12 manually.',
          mbError, MB_OK);
    end;

    // ── Step 2: 安装 TAP-Windows 驱动 ────────────────────
    if not TAPInstalled then
    begin
      TAPExe := TmpDir + '\tap-windows-installer.exe';
      if FileExists(TAPExe) then
      begin
        WizardForm.StatusLabel.Caption := ExpandConstant('{cm:InstallingTAP}');
        Exec(TAPExe, '/S', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        if ResultCode <> 0 then
          MsgBox(
            'TAP-Windows driver installation failed (exit code: ' + IntToStr(ResultCode) + ').' + #13#10 +
            'OpenVPN may not work correctly.' + #13#10 +
            'You can install the TAP driver manually from:' + #13#10 +
            'https://openvpn.net/community-downloads/',
            mbError, MB_OK);
      end else
        MsgBox(
          'TAP-Windows installer not found inside the package.' + #13#10 +
          'Expected path: ' + TAPExe + #13#10 +
          'Please install the TAP driver manually.',
          mbError, MB_OK);
    end;

    // ── Step 3: 安装 Python 依赖 ──────────────────────────
    PythonExe := GetPythonExePath();

    WizardForm.StatusLabel.Caption := 'Upgrading pip...';
    Exec(PythonExe,
      '-m pip install --upgrade pip --quiet',
      AppDir, SW_HIDE, ewWaitUntilTerminated, ResultCode);

    WizardForm.StatusLabel.Caption := ExpandConstant('{cm:InstallingDeps}');
    if FileExists(AppDir + '\requirements.txt') then
    begin
      Exec(PythonExe,
        '-m pip install -r "' + AppDir + '\requirements.txt" --quiet',
        AppDir, SW_HIDE, ewWaitUntilTerminated, ResultCode);
      if ResultCode <> 0 then
        Exec(PythonExe,
          '-m pip install PyQt5 --quiet',
          AppDir, SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end else
      Exec(PythonExe,
        '-m pip install PyQt5 --quiet',
        AppDir, SW_HIDE, ewWaitUntilTerminated, ResultCode);

    WizardForm.StatusLabel.Caption := '';
  end;
end;

// ── 卸载前询问是否保留用户配置 ───────────────────────────
function InitializeUninstall(): Boolean;
begin
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode:  Integer;
  AppDataPath: String;
  KeepData:    Boolean;
  NSSMPath:    String;
begin
  if CurUninstallStep = usUninstall then
  begin
    // ── 停止并删除 OV2NService ───────────────────────────
    NSSMPath := ExpandConstant('{app}\resources\nssm\win64\nssm.exe');
    if not FileExists(NSSMPath) then
      NSSMPath := ExpandConstant('{app}\resources\nssm\nssm.exe');

    if FileExists(NSSMPath) then
    begin
      Exec('net',    'stop OV2NService',          '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Exec(NSSMPath, 'remove OV2NService confirm', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end else
    begin
      Exec('net', 'stop OV2NService',   '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Exec('sc',  'delete OV2NService', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;

    // ── 停止 xray 进程 ────────────────────────────────────
    Exec('taskkill', '/F /IM xray.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

    // ── 询问是否保留用户配置 ─────────────────────────────
    AppDataPath := ExpandConstant('{userappdata}\ov2n');
    if DirExists(AppDataPath) then
    begin
      KeepData := MsgBox(ExpandConstant('{cm:UninstallKeepData}'),
        mbConfirmation, MB_YESNO) = IDYES;
      if not KeepData then
        DelTree(AppDataPath, True, True, True);
    end;
  end;

  // ── 卸载完成后删除安装目录 ────────────────────────────
  if CurUninstallStep = usPostUninstall then
  begin
    if DirExists(ExpandConstant('{app}')) then
      DelTree(ExpandConstant('{app}'), True, True, True);
  end;
end;
