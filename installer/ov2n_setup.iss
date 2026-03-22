; ============================================================
; ov2n - VPN Client Installer
; Inno Setup Script
; 构建命令: ISCC.exe installer\ov2n_setup.iss
; 输出目录: dist\
; ============================================================

#define MyAppName      "ov2n"
#define MyAppVersion   "1.4.2"
#define MyAppPublisher "Alfiy"
#define MyAppURL       "https://github.com/alfiy/pyQt_vpnv2ray_client"
#define MyAppExeName   "ov2n_launcher.vbs"
; MyAppIcon is built dynamically using {#SourcePath} - see SetupIconFile below

; Python 安装包路径
#define PythonInstaller "resources\python\python-3.12.10-amd64.exe"

[Setup]
; 所有相对路径均相对于项目根目录（installer\ 的上一级）
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
; PrivilegesRequired=lowest 配合 PrivilegesRequiredOverridesAllowed
; 实现在安装向导里动态选择
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; ── 默认安装目录 ──────────────────────────────────────────
; {autopf}  = 管理员模式下解析为 %ProgramFiles%
;             普通用户模式下解析为 %LOCALAPPDATA%\Programs
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
; WizardSmallImageFile={#MyAppIcon}
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
; 安装前关闭正在运行的实例
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.bat
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ── 自定义消息 ────────────────────────────────────────────
[CustomMessages]
InstallPython=Python 3 is not installed. The installer will automatically install Python 3.12.10.
InstallingPython=Installing Python 3.12.10, please wait...
InstallingTAP=Installing TAP-Windows driver...
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
Source: "..\ov2n_launcher.vbs";           DestDir: "{app}";           Flags: ignoreversion
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

; ── TAP-Windows 驱动（仅在需要时运行，不解压到安装目录）──
; 用 {tmp} 临时目录运行，安装完成后自动清理
Source: "..\resources\tap-windows\tap-windows-installer.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall skipifsourcedoesntexist

; ── Windows 脚本 ──────────────────────────────────────────
Source: "..\scripts\windows\*";           DestDir: "{app}\scripts\windows";  Flags: ignoreversion recursesubdirs createallsubdirs

; ── Python 安装包（仅当 Python 未安装时使用）────────────
Source: "..\{#PythonInstaller}";       DestDir: "{tmp}";           Flags: deleteafterinstall skipifsourcedoesntexist

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
; ============================================================
[Icons]
; 开始菜单
Name: "{group}\{#MyAppName} VPN Client";  Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\resources\images\ov2n.ico"; Comment: "ov2n - OpenVPN + Xray VPN Client"
Name: "{group}\卸载 {#MyAppName}";        Filename: "{uninstallexe}"

; 桌面快捷方式（可选，由用户在向导中勾选）
Name: "{autodesktop}\{#MyAppName} VPN Client"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\resources\images\ov2n.ico"; Tasks: desktopicon

; 开始菜单启动文件夹（开机自启，可选）
Name: "{userstartup}\{#MyAppName} VPN Client"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\resources\images\ov2n.ico"; Tasks: startup

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
; 记录安装路径供 Python 脚本使用（写入 HKCU，无需管理员）
Root: HKCU; Subkey: "Software\ov2n"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\ov2n"; ValueType: string; ValueName: "Version";    ValueData: "{#MyAppVersion}"

; ============================================================
; 安装步骤（Pascal 脚本）
; ============================================================
[Code]

// ── 全局变量 ─────────────────────────────────────────────
var
  PythonInstalled: Boolean;
  TAPInstalled: Boolean;

// ── 检测 Python 是否已安装 ───────────────────────────────
function IsPythonInstalled(): Boolean;
var
  PythonPath: String;
  ResultCode: Integer;
begin
  Result := False;

  // 检查注册表中的 Python 安装记录（Python 3.x 64位）
  if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.12\InstallPath', '', PythonPath) then
  begin
    Result := True; Exit;
  end;
  if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.11\InstallPath', '', PythonPath) then
  begin
    Result := True; Exit;
  end;
  if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.10\InstallPath', '', PythonPath) then
  begin
    Result := True; Exit;
  end;
  if RegQueryStringValue(HKCU, 'SOFTWARE\Python\PythonCore\3.12\InstallPath', '', PythonPath) then
  begin
    Result := True; Exit;
  end;
  if RegQueryStringValue(HKCU, 'SOFTWARE\Python\PythonCore\3.11\InstallPath', '', PythonPath) then
  begin
    Result := True; Exit;
  end;
  if RegQueryStringValue(HKCU, 'SOFTWARE\Python\PythonCore\3.10\InstallPath', '', PythonPath) then
  begin
    Result := True; Exit;
  end;

  // 尝试运行 python --version 作为兜底检测
  if Exec('python', '--version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    if ResultCode = 0 then
    begin
      Result := True; Exit;
    end;
  end;
end;

// ── 检测 TAP 驱动是否已安装 ──────────────────────────────
function IsTAPInstalled(): Boolean;
var
  TAPVersion: String;
begin
  Result := False;
  // 检查 TAP-Windows 注册表项
  if RegQueryStringValue(HKLM, 'SOFTWARE\TAP-Windows', 'Version', TAPVersion) then
  begin
    Result := True; Exit;
  end;
  // 检查 OpenVPN TAP 适配器
  if RegQueryStringValue(HKLM, 'SOFTWARE\OpenVPN\TapAdapter', '', TAPVersion) then
  begin
    Result := True; Exit;
  end;
end;

// ── 安装开始前的初始化 ────────────────────────────────────
procedure InitializeWizard();
begin
  PythonInstalled := IsPythonInstalled();
  TAPInstalled := IsTAPInstalled();
end;

// ── 安装步骤执行 ─────────────────────────────────────────
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  TmpDir:     String;
  PythonExe:  String;
  TAPExe:     String;
begin
  if CurStep = ssInstall then
  begin
    TmpDir := ExpandConstant('{tmp}');

    // ── Step 1: 安装 Python（如果未安装）──────────────────
    if not PythonInstalled then
    begin
      PythonExe := TmpDir + '\python-3.12.10-amd64.exe';
      if FileExists(PythonExe) then
      begin
        WizardForm.StatusLabel.Caption := ExpandConstant('{cm:InstallingPython}');
        // /quiet          - 静默安装，无 UI
        // InstallAllUsers=0 / 1 由安装模式决定
        // PrependPath=1   - 自动添加到 PATH
        // Include_test=0  - 不安装测试套件（节省空间）
        if IsAdminInstallMode() then
        begin
          Exec(PythonExe,
            '/quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_pip=1',
            '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        end
        else
        begin
          Exec(PythonExe,
            '/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1',
            '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        end;
      end;
    end;

    // ── Step 2: 安装 TAP-Windows 驱动（如果未安装）────────
    if not TAPInstalled then
    begin
      TAPExe := TmpDir + '\tap-windows-installer.exe';
      if FileExists(TAPExe) then
      begin
        WizardForm.StatusLabel.Caption := ExpandConstant('{cm:InstallingTAP}');
        // /S = 静默安装
        Exec(TAPExe, '/S', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      end;
    end;
  end;

  // ── Step 3: 安装完成后的配置 ──────────────────────────
  if CurStep = ssPostInstall then
  begin
    // 创建日志目录（如果不存在）
    ForceDirectories(ExpandConstant('{app}\logs'));

    // 确保脚本有正确的行尾符（CRLF）
    // 这里不做额外处理，build_installer.bat 在打包前已处理
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
    // 先尝试用 NSSM 删除服务
    NSSMPath := ExpandConstant('{app}\resources\nssm\win64\nssm.exe');
    if not FileExists(NSSMPath) then
      NSSMPath := ExpandConstant('{app}\resources\nssm\nssm.exe');

    if FileExists(NSSMPath) then
    begin
      // 先停止服务
      Exec('net', 'stop OV2NService', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      // 再删除服务
      Exec(NSSMPath, 'remove OV2NService confirm', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end
    else
    begin
      // NSSM 不存在时用 sc 删除
      Exec('net', 'stop OV2NService', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Exec('sc', 'delete OV2NService', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
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
      begin
        DelTree(AppDataPath, True, True, True);
      end;
    end;
  end;
end;

