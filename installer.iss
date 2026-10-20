; Bộ cài QT PDF Pro (Inno Setup 6) — cài theo người dùng, KHÔNG cần quyền quản trị (UAC).
; Biên dịch: python tools/build_release.py   (hoặc: iscc /DAppVersion=1.0.0 installer.iss sau khi chạy build.bat)
; Kết quả : dist\QTPdfPro_Setup.exe        Cài im lặng: QTPdfPro_Setup.exe /SILENT  hoặc  /VERYSILENT /SUPPRESSMSGBOXES
;
; Khoá registry ở mục [Registry] phải trùng qtpdfpro/core/file_assoc.py:registry_entries() (test đối chiếu).
; AppId phải trùng qtpdfpro/core/update_check.py:INNO_APP_ID (trình cập nhật ghi DisplayVersion vào khoá gỡ cài).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "dist\QTPdfPro"
#endif
#define AppName "QT PDF Pro"
#define AppExe "QTPdfPro.exe"
#define ProgId "QTPdfPro.PDF"
#define RegAppName "QTPdfPro"
#define CapKey "Software\QTPdfPro\Capabilities"
#define AppDesc "Đọc PDF tốc độ cao, chuyển PDF sang Word chuẩn xác, in, chỉnh sửa và công cụ văn phòng."
#define TypeName "Tài liệu PDF (QT PDF Pro)"
#define RepoUrl "https://github.com/quangthoai1985/QTPdfPro"

[Setup]
AppId={{A23779E2-FE6A-4983-9D0C-82D2465C4D8B}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Quang Thoại (quangthoai1985)
AppPublisherURL={#RepoUrl}
AppSupportURL={#RepoUrl}/issues
AppUpdatesURL={#RepoUrl}/releases
AppCopyright=MIT License
VersionInfoVersion={#AppVersion}.0
VersionInfoProductName={#AppName}
VersionInfoDescription=Bộ cài {#AppName}
; Cài theo người dùng: %LOCALAPPDATA%\Programs\QT PDF Pro — trình cập nhật ngầm thay được thư mục mà không cần UAC
PrivilegesRequired=lowest
UsedUserAreasWarning=no
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
DefaultGroupName={#AppName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=dist
OutputBaseFilename=QTPdfPro_Setup
SetupIconFile=qtpdfpro\ui\assets\app_icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ChangesAssociations=yes
; Trùng APP_MUTEX_NAME trong qtpdfpro/ui/app.py: bộ cài / gỡ cài đặt nhận ra ứng dụng đang mở
AppMutex=QTPdfPro.AppMutex
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "vietnamese"; MessagesFile: "compiler:Default.isl,installer\Vietnamese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Cài đè bản cũ: xoá bộ thư viện cũ để không lẫn tệp của phiên bản trước
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "{#AppDesc}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; ProgID «QTPdfPro.PDF»
Root: HKCU; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueName: ""; ValueData: "{#TypeName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueName: "FriendlyTypeName"; ValueData: "{#TypeName}"
Root: HKCU; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"",0"
Root: HKCU; Subkey: "Software\Classes\{#ProgId}\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"
Root: HKCU; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""
; Danh sách «Open with» của .pdf
Root: HKCU; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"",0"
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""
; Capabilities + RegisteredApplications → ứng dụng hiện trong Cài đặt › Ứng dụng mặc định
Root: HKCU; Subkey: "Software\QTPdfPro"; Flags: uninsdeletekey
Root: HKCU; Subkey: "{#CapKey}"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#AppName}"
Root: HKCU; Subkey: "{#CapKey}"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "{#AppDesc}"
Root: HKCU; Subkey: "{#CapKey}"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: """{app}\{#AppExe}"",0"
Root: HKCU; Subkey: "{#CapKey}\FileAssociations"; ValueType: string; ValueName: ".pdf"; ValueData: "{#ProgId}"
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#RegAppName}"; ValueData: "{#CapKey}"; Flags: uninsdeletevalue
; Win+R «QTPdfPro»
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#AppExe}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe}"; Flags: uninsdeletekey

[Run]
; Windows không cho ứng dụng tự đặt mình làm mặc định — mở thẳng trang «Ứng dụng mặc định» của QT PDF Pro
; để người dùng bấm «Đặt mặc định» một lần (bỏ qua khi cài im lặng hoặc khi đã là mặc định).
Filename: "ms-settings:defaultapps?registeredAppUser={#RegAppName}"; Description: "{cm:SetDefaultPdf}"; Flags: shellexec postinstall skipifsilent nowait; Check: not IsDefaultPdfApp
Filename: "{app}\{#AppExe}"; Parameters: "--skip-default-prompt"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
Type: filesandordirs; Name: "{app}.old"
; Bộ đệm tải bản cập nhật ngầm (%LOCALAPPDATA%\QT PDF Pro\updates)
Type: filesandordirs; Name: "{localappdata}\{#AppName}"

[Code]
function IsDefaultPdfApp(): Boolean;
var
  ProgIdValue: String;
begin
  Result := False;
  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pdf\UserChoiceLatest', 'ProgId', ProgIdValue) then
    Result := CompareText(ProgIdValue, '{#ProgId}') = 0
  else if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pdf\UserChoice', 'ProgId', ProgIdValue) then
    Result := CompareText(ProgIdValue, '{#ProgId}') = 0;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  SettingsDir: String;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  // Thiết lập người dùng (%LOCALAPPDATA%\QTPdfPro): hỏi trước khi xoá; gỡ im lặng thì giữ lại
  SettingsDir := ExpandConstant('{localappdata}\QTPdfPro');
  if DirExists(SettingsDir) and not UninstallSilent() then
    if MsgBox(CustomMessage('RemoveSettings'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(SettingsDir, True, True, True);
end;
