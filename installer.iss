; XP Analyzer installer — built with Inno Setup.
;
; To build:  Installer.bat  (or ISCC.exe installer.iss)
; Output:    installer\XP-Analyzer-Setup.exe
;
; Installs PER USER (never asks for administrator), so a double click just
; works, with no Windows permission prompt.

#define AppName "XP Analyzer"
#define AppVersion "2.0.0"
#define Publisher "victorharry"
#define ExeName "XP Analyzer.exe"

[Setup]
AppId={{8F3A61C2-4D7E-4B9A-9E21-XPANALYZER01}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename=XP-Analyzer-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#ExeName}
; The wizard's final page is the one place the user is guaranteed to read,
; so that is where the "run as administrator" note goes
InfoAfterFile=SETUP.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; \
    GroupDescription: "Shortcuts:"

[Files]
; the whole PyInstaller folder: the .exe alone will not run, it needs _internal
Source: "dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "SETUP.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#ExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#ExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ExeName}"; Description: "Launch {#AppName} now"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; settings live here; they go away with the uninstall
Type: filesandordirs; Name: "{userappdata}\{#AppName}"
