; J.A.R.V.I.S. Gast - Setup (Mark 5, Schritt C5). Gebaut mit Inno Setup 6 (kostenlos, nur Windows): Datei oeffnen, "Build > Compile".
; Ergebnis: installer\output\JarvisGast-Setup.exe
;
; Was dieses Setup tut: eine Verknuepfung anlegen, die Edge (sonst Chrome) als eigenes App-Fenster auf den Jarvis-Server von Moritz oeffnet.
; Was es NICHT enthaelt: keinen Server, kein Python, keine Zugangsdaten, keine Schluessel. Angemeldet wird erst in der App, mit einem Code von Moritz.
; Es braucht keine Administratorrechte (alles landet im Benutzerordner) und aendert nichts am Rest des Rechners.

#define AppName "J.A.R.V.I.S. Gast"
#define AppVersion "Mark 5"
#define DefaultHost "gott-desktop.taild3a628.ts.net"

[Setup]
AppId={{6B0F3C52-8E4A-4D7B-9A15-2C7E5F1D9B38}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Moritz
VersionInfoVersion=5.0.0.0
DefaultDirName={localappdata}\JarvisGast
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=JarvisGast-Setup
SetupIconFile=jarvis.ico
UninstallDisplayIcon={app}\jarvis.ico
UninstallDisplayName={#AppName} ({#AppVersion})
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
#if FileExists(CompilerPath + "Languages\German.isl")
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
#else
Name: "english"; MessagesFile: "compiler:Default.isl"
#endif

[Files]
Source: "jarvis.ico"; DestDir: "{app}"; Flags: ignoreversion

[Tasks]
Name: "desktopicon"; Description: "Verknüpfung auf dem Desktop anlegen"; GroupDescription: "Zusätzliche Verknüpfungen:"

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{code:BrowserPath}"; Parameters: "{code:BrowserParams}"; IconFilename: "{app}\jarvis.ico"; Comment: "J.A.R.V.I.S. (Testbereich)"
Name: "{userdesktop}\{#AppName}"; Filename: "{code:BrowserPath}"; Parameters: "{code:BrowserParams}"; IconFilename: "{app}\jarvis.ico"; Tasks: desktopicon

[Run]
Filename: "{code:BrowserPath}"; Parameters: "{code:BrowserParams}"; Description: "{#AppName} jetzt starten"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; Der eigene Browser-Ordner der App (Anmeldung, Zwischenspeicher) geht mit
Type: filesandordirs; Name: "{app}\Profil"

[Code]
var
  HostPage: TInputQueryWizardPage;

function CleanHost(Text: String): String;
begin
  Result := Lowercase(Trim(Text));
  if Pos('https://', Result) = 1 then Delete(Result, 1, 8);
  if Pos('http://', Result) = 1 then Delete(Result, 1, 7);
  while (Length(Result) > 0) and (Result[Length(Result)] = '/') do
    Delete(Result, Length(Result), 1);
end;

// Tailscale-Namen enden immer auf .ts.net: so kann die App nie auf eine fremde Seite zeigen
function EndsWithTailnet(Host: String): Boolean;
begin
  Result := (Length(Host) > 7) and (Copy(Host, Length(Host) - 6, 7) = '.ts.net');
end;

function HostLooksValid(Host: String): Boolean;
var
  I: Integer;
  C: Char;
begin
  Result := (Length(Host) >= 4) and (Length(Host) <= 120) and (Pos('.', Host) > 1);
  if not Result then Exit;
  for I := 1 to Length(Host) do
  begin
    C := Host[I];
    if not (((C >= 'a') and (C <= 'z')) or ((C >= '0') and (C <= '9')) or (C = '.') or (C = '-')) then
    begin
      Result := False;
      Exit;
    end;
  end;
  if (Host[1] = '.') or (Host[1] = '-') or (Host[Length(Host)] = '.') or (Host[Length(Host)] = '-') then
    Result := False;
  if not EndsWithTailnet(Host) then
    Result := False;
end;

function GetHost(Param: String): String;
begin
  if HostPage <> nil then
    Result := CleanHost(HostPage.Values[0])
  else
    Result := '{#DefaultHost}';
end;

function FirstExisting(const Paths: array of String): String;
var
  I: Integer;
begin
  Result := '';
  for I := 0 to GetArrayLength(Paths) - 1 do
    if FileExists(Paths[I]) then
    begin
      Result := Paths[I];
      Exit;
    end;
end;

// Edge ist bei Windows 10/11 immer dabei, sonst nehmen wir Chrome.
function BrowserPath(Param: String): String;
begin
  Result := FirstExisting([
    ExpandConstant('{commonpf32}\Microsoft\Edge\Application\msedge.exe'),
    ExpandConstant('{commonpf64}\Microsoft\Edge\Application\msedge.exe'),
    ExpandConstant('{commonpf32}\Google\Chrome\Application\chrome.exe'),
    ExpandConstant('{commonpf64}\Google\Chrome\Application\chrome.exe'),
    ExpandConstant('{localappdata}\Google\Chrome\Application\chrome.exe')
  ]);
end;

// App-Fenster ohne Adressleiste, mit eigenem Profilordner (eigene Anmeldung, nichts vermischt mit dem normalen Browser)
function BrowserParams(Param: String): String;
begin
  Result := '--app=https://' + GetHost('') + '/ --no-first-run --user-data-dir="' + ExpandConstant('{app}\Profil') + '"';
end;

function TailscaleInstalled: Boolean;
begin
  Result := FileExists(ExpandConstant('{commonpf64}\Tailscale\tailscale.exe')) or
            FileExists(ExpandConstant('{commonpf32}\Tailscale\tailscale.exe')) or
            FileExists(ExpandConstant('{commonpf}\Tailscale\tailscale-ipn.exe'));
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  if BrowserPath('') = '' then
  begin
    MsgBox('Weder Microsoft Edge noch Google Chrome wurden gefunden. Bitte installiere einen von beiden und starte das Setup noch einmal.', mbError, MB_OK);
    Result := False;
  end;
end;

procedure InitializeWizard;
begin
  HostPage := CreateInputQueryPage(wpWelcome, 'Server', 'Adresse des Jarvis-Servers',
    'Diese Adresse hast du von Moritz bekommen. Sie sieht so aus: name.tailabc12.ts.net');
  HostPage.Add('Adresse:', False);
  HostPage.Values[0] := GetPreviousData('Host', '{#DefaultHost}');     // bei einem Update die Adresse von letztes Mal
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  SetPreviousData(PreviousDataKey, 'Host', GetHost(''));
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (HostPage <> nil) and (CurPageID = HostPage.ID) then
  begin
    if not HostLooksValid(CleanHost(HostPage.Values[0])) then
    begin
      MsgBox('Das sieht nicht wie eine Tailscale-Adresse aus. Erwartet wird zum Beispiel: name.tailabc12.ts.net (endet auf .ts.net, ohne https:// und ohne Leerzeichen).', mbError, MB_OK);
      Result := False;
    end
    else if not TailscaleInstalled then
      Result := MsgBox('Tailscale scheint auf diesem Computer nicht installiert zu sein. Ohne Tailscale (und ohne Einladung von Moritz) erreicht die App den Server nicht.' + #13#10#13#10 +
                       'Download: tailscale.com/download' + #13#10#13#10 + 'Trotzdem weitermachen?', mbConfirmation, MB_YESNO) = IDYES;
  end;
end;
