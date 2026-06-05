#define MyAppName "A3Agent"
#define MyAppVersion GetEnv("A3AGENT_VERSION")
#if MyAppVersion == ""
#define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "FroStorM"
#define MyAppURL "https://github.com/FroStorM/A3Agent"
#define MyAppExeName "A3Agent.exe"
#define SourceDir GetEnv("A3AGENT_SOURCE_DIR")
#if SourceDir == ""
#define SourceDir "..\\dist\\windows\\A3Agent"
#endif
#define OutputDir GetEnv("A3AGENT_OUTPUT_DIR")
#if OutputDir == ""
#define OutputDir "..\\release"
#endif
#define OutputBase GetEnv("A3AGENT_OUTPUT_BASE")
#if OutputBase == ""
#define OutputBase "A3Agent_Setup"
#endif

[Setup]
AppId={{8C7D3C64-8753-49D1-A6A8-4E7D69D1F6D7}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBase}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\dist\A3Agent-windows.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=A3Agent Windows installer
VersionInfoProductName={#MyAppName}
CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName}

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Keep user data in %APPDATA%\A3Agent so upgrades/uninstalls do not remove API keys,
; conversations, backups, workspace history, or desktop pet settings.
