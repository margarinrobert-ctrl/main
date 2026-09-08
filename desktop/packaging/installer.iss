; Inno Setup script for Trading Backtester.
;
; Produces dist/TradingBacktesterSetup.exe from the PyInstaller onedir output in
; dist/TradingBacktester/.  Build the app first, then:
;     iscc packaging\installer.iss
;
; The installer is per-user by default (PrivilegesRequired=lowest) so it needs
; no administrator prompt, which is what most people want for a desktop tool and
; what lets it install on a locked-down work machine.

#define MyAppName "Trading Backtester"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Trading Backtester"
#define MyAppExeName "TradingBacktester.exe"

[Setup]
AppId={{8E0B4C21-6F3D-4A7E-9C1B-2D5A7F0E9B31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=TradingBacktesterSetup
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
MinVersion=10.0
LicenseFile=..\LICENSE
InfoBeforeFile=..\packaging\installer_notice.txt
AppReadmeFile={app}\README.md

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; \
    GroupDescription: "Additional shortcuts:"
Name: "associatetbs"; Description: "Associate .tbs strategy files with {#MyAppName}"; \
    GroupDescription: "File associations:"; Flags: unchecked

[Files]
Source: "..\dist\TradingBacktester\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\TradingBacktester\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} Documentation"; Filename: "{app}\README.md"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.tbs"; ValueType: string; ValueName: ""; \
    ValueData: "TradingBacktester.Strategy"; Flags: uninsdeletevalue; Tasks: associatetbs
Root: HKA; Subkey: "Software\Classes\TradingBacktester.Strategy"; ValueType: string; \
    ValueName: ""; ValueData: "Trading Backtester Strategy"; \
    Flags: uninsdeletekey; Tasks: associatetbs
Root: HKA; Subkey: "Software\Classes\TradingBacktester.Strategy\DefaultIcon"; \
    ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associatetbs
Root: HKA; Subkey: "Software\Classes\TradingBacktester.Strategy\shell\open\command"; \
    ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; \
    Tasks: associatetbs

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove only what the installer created.  The user's workspace lives in
; Documents\TradingBacktester and is deliberately left alone -- uninstalling the
; application must never delete somebody's strategies and backtests.
Type: filesandordirs; Name: "{app}\_internal"
