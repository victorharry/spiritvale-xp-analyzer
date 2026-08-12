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

[Code]
{ ---------------------------------------------------------------------------
  O XP Analyzer le os pacotes que o servidor do jogo ja manda pra maquina.
  O Windows so libera isso de dois jeitos: com um leitor de rede instalado
  (o Npcap), ou rodando o programa como administrador TODA VEZ.

  Instalar o Npcap aqui, uma vez, e o que faz o programa abrir normal daqui
  pra frente. Sem isso o usuario tem que descobrir sozinho por que "nao
  aparece nada" — e essa e a pior experiencia possivel.

  Se o download falhar (sem internet, site fora), a instalacao SEGUE. O
  programa funciona rodando como administrador e diz isso na propria janela.
  --------------------------------------------------------------------------- }

const
  URL_NPCAP = 'https://npcap.com/dist/npcap-1.82.exe';

var
  PaginaBaixando: TDownloadWizardPage;
  BaixouNpcap: Boolean;

function LeitorDeRedePresente(): Boolean;
begin
  { as duas pastas onde o Npcap pode ficar, com ou sem modo compativel }
  Result := FileExists(ExpandConstant('{sys}\wpcap.dll')) or
            FileExists(ExpandConstant('{sys}\Npcap\wpcap.dll'));
end;

function AoBaixar(const Url, NomeArquivo: String; const Progresso, Total: Int64): Boolean;
begin
  Result := True;
end;

procedure InitializeWizard();
begin
  BaixouNpcap := False;
  PaginaBaixando := CreateDownloadPage(
    'Componente de leitura de rede',
    'Baixando o que o XP Analyzer precisa para ler seu progresso',
    @AoBaixar);
end;

function NextButtonClick(PaginaAtual: Integer): Boolean;
begin
  Result := True;
  if (PaginaAtual = wpReady) and (not LeitorDeRedePresente()) then
  begin
    PaginaBaixando.Clear;
    PaginaBaixando.Add(URL_NPCAP, 'npcap-setup.exe', '');
    PaginaBaixando.Show;
    try
      try
        PaginaBaixando.Download;
        BaixouNpcap := True;
      except
        { sem internet ou site fora: nao trava a instalacao }
        BaixouNpcap := False;
      end;
    finally
      PaginaBaixando.Hide;
    end;
  end;
end;

procedure CurStepChanged(Passo: TSetupStep);
var
  Codigo: Integer;
begin
  if (Passo = ssPostInstall) and BaixouNpcap then
  begin
    { Uma opcao do instalador do Npcap decide se isso vai funcionar: com
      "Restrict... to Administrators only" MARCADA, abrir a placa continua
      exigindo elevacao e todo o proposito se perde. Por isso ela e citada pelo
      nome, em vez de um generico "aceite o que ele sugerir". }
    MsgBox('Falta um passo: o instalador do leitor de rede (Npcap) vai abrir.' + #13#10 + #13#10 +
           'IMPORTANTE: deixe DESMARCADA a opcao' + #13#10 +
           '   "Restrict Npcap driver''s access to Administrators only"' + #13#10 + #13#10 +
           'As outras podem ficar como estao. Depois e so clicar em Install.' + #13#10 + #13#10 +
           'Sem esse componente, o XP Analyzer so funciona se voce abrir o' + #13#10 +
           'programa como administrador toda vez.',
           mbInformation, MB_OK);
    Exec(ExpandConstant('{tmp}\npcap-setup.exe'), '', '',
         SW_SHOW, ewWaitUntilTerminated, Codigo);
  end;
end;
