[Setup]
AppName=Seraphina.AGI Guardian Copilot
AppVersion=1.1.1
AppVerName=Seraphina.AGI Guardian Copilot v1.1.1
DefaultDirName={pf}\Seraphina AGI
OutputDir=installer
OutputBaseFilename=SeraphinaAGI-Guardian-v1.1.1
Compression=lzma
SolidCompression=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\Seraphina_AGI.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Seraphina AGI"; Filename: "{app}\Seraphina_AGI.exe"
Name: "{commondesktop}\Seraphina AGI"; Filename: "{app}\Seraphina_AGI.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Seraphina_AGI.exe"; Description: "{cm:LaunchProgram,Seraphina AGI}"; Flags: nowait postinstall skipifsilent
