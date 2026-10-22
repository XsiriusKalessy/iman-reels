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

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "..\dist\Iman\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Imán"; Filename: "{app}\Iman.exe"
Name: "{autodesktop}\Imán"; Filename: "{app}\Iman.exe"

[Run]
Filename: "{app}\Iman.exe"; Description: "Abrir Imán"; Flags: nowait postinstall skipifsilent
