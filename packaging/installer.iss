#define MyAppName "FastVideoCropper"
#include "..\build\downloads.iss"

[Setup]
AppId=electblake.FastVideoCropper
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist\installer
OutputBaseFilename=FastVideoCropper-{#MyAppVersion}-windows-amd64-Setup
UninstallDisplayIcon={app}\application\src\fastvideocropper\FastVideoCropper.ico
SetupIconFile=..\src\fastvideocropper\FastVideoCropper.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
ArchiveExtraction=full
InfoBeforeFile=online-install.txt
SetupLogging=yes

[Files]
Source: "..\pyproject.toml"; DestDir: "{app}\application"; Flags: ignoreversion
Source: "..\uv.lock"; DestDir: "{app}\application"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}\application"; Flags: ignoreversion
Source: "..\CHANGELOG.md"; DestDir: "{app}\application"; Flags: ignoreversion
Source: "..\src\fastvideocropper\*.py"; DestDir: "{app}\application\src\fastvideocropper"; Flags: ignoreversion
Source: "..\src\fastvideocropper\*.ico"; DestDir: "{app}\application\src\fastvideocropper"; Flags: ignoreversion
Source: "THIRD-PARTY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "uv.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "vendor.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#UvUrl}"; DestDir: "{app}\tools\uv"; DestName: "uv.zip"; ExternalSize: {#UvSize}; Hash: "{#UvHash}"; Flags: external download extractarchive ignoreversion recursesubdirs createallsubdirs
Source: "{#FFmpegUrl}"; DestDir: "{app}\tools\ffmpeg"; DestName: "ffmpeg.zip"; ExternalSize: {#FFmpegSize}; Hash: "{#FFmpegHash}"; Flags: external download extractarchive ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\application\.venv\Scripts\pythonw.exe"; Parameters: "-I -m fastvideocropper.installed"; WorkingDir: "{app}"; IconFilename: "{app}\application\src\fastvideocropper\FastVideoCropper.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\application\.venv\Scripts\pythonw.exe"; Parameters: "-I -m fastvideocropper.installed"; WorkingDir: "{app}"; IconFilename: "{app}\application\src\fastvideocropper\FastVideoCropper.ico"; Tasks: desktopicon

[InstallDelete]
Type: files; Name: "{app}\FastVideoCropper.exe"
Type: filesandordirs; Name: "{app}\_internal"

[Run]
Filename: "{app}\tools\uv\uv.exe"; Parameters: "python install 3.13.12 --install-dir ""{app}\python"" --no-bin --no-registry --no-config --no-cache"; StatusMsg: "Downloading Python 3.13.12..."; Flags: runhidden logoutput
Filename: "{app}\tools\uv\uv.exe"; Parameters: "sync --project ""{app}\application"" --python ""{app}\python\cpython-3.13.12-windows-x86_64-none\python.exe"" --no-python-downloads --locked --no-dev --no-editable --no-config --no-cache"; StatusMsg: "Installing locked Python dependencies..."; Flags: runhidden logoutput
Filename: "{app}\application\.venv\Scripts\pythonw.exe"; Parameters: "-I -m fastvideocropper.installed"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\application\.venv"
Type: filesandordirs; Name: "{app}\python"

[Registry]
Root: HKCU; Subkey: "Software\Classes\Directory\shell\FastVideoCropper"; Flags: dontcreatekey uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\FastVideoCropper"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\application\src\fastvideocropper\FastVideoCropper.ico"""; Flags: dontcreatekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\FastVideoCropper\command"; ValueType: string; ValueData: """{app}\application\.venv\Scripts\pythonw.exe"" -I -m fastvideocropper.installed ""%1"""; Flags: dontcreatekey
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\FastVideoCropper"; Flags: dontcreatekey uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\FastVideoCropper"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\application\src\fastvideocropper\FastVideoCropper.ico"""; Flags: dontcreatekey
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\FastVideoCropper\command"; ValueType: string; ValueData: """{app}\application\.venv\Scripts\pythonw.exe"" -I -m fastvideocropper.installed ""%V"""; Flags: dontcreatekey
Root: HKCU; Subkey: "Software\Classes\Drive\shell\FastVideoCropper"; Flags: dontcreatekey uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Drive\shell\FastVideoCropper"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\application\src\fastvideocropper\FastVideoCropper.ico"""; Flags: dontcreatekey
Root: HKCU; Subkey: "Software\Classes\Drive\shell\FastVideoCropper\command"; ValueType: string; ValueData: """{app}\application\.venv\Scripts\pythonw.exe"" -I -m fastvideocropper.installed ""%1"""; Flags: dontcreatekey
