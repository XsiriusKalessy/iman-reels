; Instalador de Windows (Inno Setup). Lo genera el flujo de GitHub Actions.
#define Version GetEnv("IMAN_VERSION")

[Setup]
AppId={{6F3C2A91-5D1E-4B7A-9C3E-1A2B3C4D5E6F}
AppName=Imán
AppVersion={#Version}
AppPublisher=Imán Reels
AppPublisherURL=https://imanreels.com
DefaultDirName={autopf}\Iman
DefaultGroupName=Imán
OutputBaseFilename=Iman-{#Version}-Windows
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern
SetupIconFile=iman.ico
; Las actualizaciones desde la app se instalan en silencio: cierra Imán, instala y lo vuelve a abrir.
CloseApplications=force
RestartApplications=no

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "..\dist\Iman\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Imán"; Filename: "{app}\Iman.exe"
Name: "{autodesktop}\Imán"; Filename: "{app}\Iman.exe"

[Run]
Filename: "{app}\Iman.exe"; Description: "Abrir Imán"; Flags: nowait postinstall skipifsilent
Filename: "{app}\Iman.exe"; Flags: nowait; Check: WizardSilent

[Code]
// Imán sigue abierto por detrás (el servidor local no tiene ventana) y Windows no deja
// reemplazar sus archivos. Lo cerramos antes de copiar nada.
procedure CloseIman();
var
  Code: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM Iman.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(1500);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  CloseIman();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  CloseIman();
  Result := True;
end;
