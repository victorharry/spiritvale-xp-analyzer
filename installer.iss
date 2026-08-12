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
; The network reader is a separate download, and the wizard's final page is
; the one place the user is guaranteed to read about it
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

[Code]
{ ---------------------------------------------------------------------------
  The XP Analyzer reads the packets the game server already sends to this
  machine. Windows only allows that in one of two ways: with a network reader
  installed (Npcap), or by running the program as administrator EVERY time.

  Installing Npcap here, once, is what lets the program open normally from now
  on. Without it the user has to work out for themselves why "nothing shows
  up" — the worst possible experience.

  If the download fails (no internet, site down), the install CONTINUES. The
  program still works when run as administrator, and says so in its own window.
  --------------------------------------------------------------------------- }

const
  NPCAP_URL = 'https://npcap.com/dist/npcap-1.82.exe';

var
  DownloadPage: TDownloadWizardPage;
  NpcapDownloaded: Boolean;

function NetworkReaderPresent(): Boolean;
begin
  { both folders Npcap may live in, with or without WinPcap-compatible mode }
  Result := FileExists(ExpandConstant('{sys}\wpcap.dll')) or
            FileExists(ExpandConstant('{sys}\Npcap\wpcap.dll'));
end;

function OnDownloadProgress(const Url, FileName: String; const Progress, Total: Int64): Boolean;
begin
  Result := True;
end;

procedure InitializeWizard();
begin
  NpcapDownloaded := False;
  DownloadPage := CreateDownloadPage(
    'Network reader',
    'Downloading what the XP Analyzer needs to read your progress',
    @OnDownloadProgress);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpReady) and (not NetworkReaderPresent()) then
  begin
    DownloadPage.Clear;
    DownloadPage.Add(NPCAP_URL, 'npcap-setup.exe', '');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
        NpcapDownloaded := True;
      except
        { offline or site down: never block the install }
        NpcapDownloaded := False;
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if (CurStep = ssPostInstall) and NpcapDownloaded then
  begin
    { One Npcap option decides whether this works at all: with "Restrict... to
      Administrators only" TICKED, opening the adapter still needs elevation
      and the whole point is lost. That is why it is named explicitly here,
      instead of a vague "accept the defaults". }
    MsgBox('One more step: the network reader (Npcap) installer will open.' + #13#10 + #13#10 +
           'IMPORTANT: leave this option UNTICKED' + #13#10 +
           '   "Restrict Npcap driver''s access to Administrators only"' + #13#10 + #13#10 +
           'The rest can stay as they are. Then click Install.' + #13#10 + #13#10 +
           'Without this component the XP Analyzer only works if you run it' + #13#10 +
           'as administrator every time.',
           mbInformation, MB_OK);
    Exec(ExpandConstant('{tmp}\npcap-setup.exe'), '', '',
         SW_SHOW, ewWaitUntilTerminated, ResultCode);
  end;
end;
