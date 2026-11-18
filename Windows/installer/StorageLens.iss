#ifndef AppVersion
#define AppVersion "1.0.0"
#endif
#ifndef PublishDirectory
#define PublishDirectory "..\..\artifacts\windows\publish"
#endif
[Setup]
AppId={{9E7C92F2-086E-4CA3-BE86-51D57620E107}
AppName=StorageLens
AppVersion={#AppVersion}
AppPublisher=Portfolio Engineering
DefaultDirName={localappdata}\Programs\StorageLens
DefaultGroupName=StorageLens
UninstallDisplayIcon={app}\StorageLens.exe
OutputDir=..\..\artifacts\downloads
OutputBaseFilename=StorageLens-Setup-{#AppVersion}-preview-win-x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
WizardStyle=modern
Compression=zip/6
SolidCompression=yes
SetupIconFile=..\StorageLens\Assets\StorageLens.ico
CloseApplications=yes
RestartApplications=no
AppMutex=StorageLens.Desktop.Installer

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#PublishDirectory}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\StorageLens"; Filename: "{app}\StorageLens.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\StorageLens"; Filename: "{app}\StorageLens.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\StorageLens.exe"; Description: "Open StorageLens"; Flags: nowait postinstall skipifsilent

; Uninstall removes installed program files. User scan records under LocalAppData
; are intentionally preserved; there is no recursive user-data deletion action.
