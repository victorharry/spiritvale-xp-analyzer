; Instalador do XP Analyzer — gerado com Inno Setup.
;
; Para compilar:  Instalador.bat  (ou ISCC.exe instalador.iss)
; Sai em:         instalador\XP-Analyzer-Setup.exe
;
; Instala por USUARIO (nao pede administrador): assim o duplo clique funciona
; direto, sem tela de permissao do Windows.

#define Nome "XP Analyzer"
#define Versao "2.0.0"
#define Autor "victorharry"
#define Exe "XP Analyzer.exe"

[Setup]
AppId={{8F3A61C2-4D7E-4B9A-9E21-XPANALYZER01}
AppName={#Nome}
AppVersion={#Versao}
AppPublisher={#Autor}
DefaultDirName={autopf}\{#Nome}
DefaultGroupName={#Nome}
DisableProgramGroupPage=yes
OutputDir=instalador
OutputBaseFilename=XP-Analyzer-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#Exe}
; a leitura exata depende do Npcap, que e um download separado — a pagina final
; do assistente e o unico lugar onde o usuario com certeza le isso
InfoAfterFile=LEIA-ME.txt

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na area de trabalho"; \
    GroupDescription: "Atalhos:"

[Files]
; a pasta inteira do PyInstaller: o .exe sozinho nao roda, precisa do _internal
Source: "dist\{#Nome}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "LEIA-ME.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#Nome}"; Filename: "{app}\{#Exe}"
Name: "{group}\Desinstalar {#Nome}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#Nome}"; Filename: "{app}\{#Exe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#Exe}"; Description: "Abrir o {#Nome} agora"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; a calibracao e os niveis ficam aqui; some junto na desinstalacao
Type: filesandordirs; Name: "{userappdata}\{#Nome}"
