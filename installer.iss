; XP Analyzer installer — built with Inno Setup.
;
; To build:  Installer.bat  (or ISCC.exe installer.iss)
; Output:    installer\XP-Analyzer-Setup.exe
;
; Installs PER USER (never asks for administrator), so a double click just
; works, with no Windows permission prompt.

#define AppName "XP Analyzer"
; keep in step with updates.py — verify_build.py refuses to package a mismatch
#define AppVersion "2.1.0"
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
; `shellexec` is required, not cosmetic: this installer runs unelevated (per
; user, by design) and the app asks for administrator in its manifest. Plain
; CreateProcess cannot start an elevated process from a non-elevated one and
; fails with code 740 — "the requested operation requires elevation".
; ShellExecute knows how to raise the UAC prompt instead.
Filename: "{app}\{#ExeName}"; Description: "Launch {#AppName} now"; \
    Flags: nowait postinstall skipifsilent shellexec

[UninstallDelete]
; settings live here; they go away with the uninstall
Type: filesandordirs; Name: "{userappdata}\{#AppName}"
