; FRIDAY installer (PLAN §75) — built by installer\build.py (passes /DAppVersion=x.y.z)
; Per-user, no admin: FRIDAY + its own voice program + voice models + default settings. During setup it downloads
; Ollama (if missing) and the LLM qwen3.5:4b, sets Ollama's "don't hog the PC" variables, and pre-downloads the
; speech-recognition models. Optional (§87): cua-driver 0.37.0 for the computer tool — the installer scripts read and
; bundled in installer\cua\, no logon task, telemetry off. Nothing personal is shipped (no data\, no secrets, default settings.json).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{2CF2BAE0-006F-4A1B-BF1F-DD371DE0DCF2}
AppName=F.R.I.D.A.Y.
AppVersion={#AppVersion}
AppVerName=F.R.I.D.A.Y. {#AppVersion}
AppPublisher=FRIDAY (local)
DefaultDirName={localappdata}\Programs\FRIDAY
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
OutputDir=..\dist\installer
OutputBaseFilename=FRIDAY-Setup-{#AppVersion}
SetupIconFile=..\assets\friday.ico
UninstallDisplayIcon={app}\FRIDAY\FRIDAY.exe
UninstallDisplayName=F.R.I.D.A.Y.
WizardStyle=modern
Compression=lzma2/normal
SolidCompression=no
LZMANumBlockThreads=4
DiskSpanning=yes
DiskSliceSize=max
; FRIDAY's own single-instance mutex: setup asks to close a running FRIDAY first
AppMutex=Local\FRIDAY_TRAY
CloseApplications=no

[Languages]
Name: "thai"; MessagesFile: "compiler:Languages\Thai.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
thai.Startup=เปิด F.R.I.D.A.Y. เองทุกครั้งที่เข้าสู่ระบบ
english.Startup=Start F.R.I.D.A.Y. when I sign in
thai.StartMenu=ทางลัดใน Start Menu (คีย์ลัด Ctrl+Alt+J)
english.StartMenu=Start Menu shortcut (hotkey Ctrl+Alt+J)
thai.GetOllama=กำลังดาวน์โหลดและติดตั้ง Ollama (ตัวรันโมเดลภาษา)…
english.GetOllama=Downloading and installing Ollama…
thai.PullModel=กำลังดาวน์โหลดสมองของ FRIDAY (qwen3.5:4b ~3.4 GB) — ดูความคืบหน้าในหน้าต่างดำ…
english.PullModel=Downloading FRIDAY's brain (qwen3.5:4b, ~3.4 GB) — progress in the console window…
thai.Prefetch=กำลังดาวน์โหลดโมเดลฟังเสียง (~3 GB)…
english.Prefetch=Downloading the speech-recognition models (~3 GB)…
thai.NoNvidia=ไม่พบการ์ดจอ NVIDIA — FRIDAY จะฟังเสียงด้วย CPU (ช้ากว่า) และ Ollama จะตอบช้าลง
english.NoNvidia=No NVIDIA GPU found — FRIDAY will transcribe on the CPU (slower) and Ollama will answer more slowly.
thai.NetFail=ดาวน์โหลดบางอย่างไม่สำเร็จ (%1) — ตรวจเน็ตแล้วติดตั้งซ้ำ หรือ FRIDAY จะโหลดเองตอนใช้ครั้งแรก
thai.CuaTask=ติดตั้ง cua-driver ให้ FRIDAY ใช้แอปแทนคุณได้ (โหลดจาก GitHub ~20 MB · ไม่ส่งสถิติ)
english.CuaTask=Install cua-driver so FRIDAY can use apps for you (from GitHub, ~20 MB, telemetry off)
thai.GetCua=กำลังติดตั้ง cua-driver…
english.GetCua=Installing cua-driver…
english.NetFail=Some downloads failed (%1) — check the internet and run setup again; FRIDAY also downloads on first use.

[Tasks]
Name: "startup"; Description: "{cm:Startup}"
Name: "startmenu"; Description: "{cm:StartMenu}"
Name: "cuadriver"; Description: "{cm:CuaTask}"; Flags: unchecked

[Files]
Source: "..\dist\FRIDAY\*"; DestDir: "{app}\FRIDAY"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\dist\FRIDAY-voice\*"; DestDir: "{app}\voice"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\skills\*"; DestDir: "{app}\skills"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "stage\config\settings.json"; DestDir: "{app}\config"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "..\models\vanira\*"; DestDir: "{app}\models\vanira"; Flags: ignoreversion
Source: "..\models\speaker\*"; DestDir: "{app}\models\speaker"; Flags: ignoreversion
Source: "..\models\piper\en_US-hfc_female-medium.onnx*"; DestDir: "{app}\models\piper"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "cua\*"; DestDir: "{tmp}\cua"; Flags: deleteafterinstall; Tasks: cuadriver

[Dirs]
Name: "{app}\data"; Flags: uninsneveruninstall

[Icons]
Name: "{userprograms}\FRIDAY"; Filename: "{app}\FRIDAY\FRIDAY.exe"; WorkingDir: "{app}\FRIDAY"; IconFilename: "{app}\assets\friday.ico"; HotKey: ctrl+alt+j; Tasks: startmenu

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "FRIDAY"; ValueData: """{app}\FRIDAY\FRIDAY.exe"""; Flags: uninsdeletevalue; Tasks: startup
; Ollama: one model at a time, one request at a time, free the GPU after 5 idle minutes (FRIDAY's "don't disturb the PC" rule)
Root: HKCU; Subkey: "Environment"; ValueType: string; ValueName: "OLLAMA_MAX_LOADED_MODELS"; ValueData: "1"
Root: HKCU; Subkey: "Environment"; ValueType: string; ValueName: "OLLAMA_NUM_PARALLEL"; ValueData: "1"
Root: HKCU; Subkey: "Environment"; ValueType: string; ValueName: "OLLAMA_MAX_QUEUE"; ValueData: "2"
Root: HKCU; Subkey: "Environment"; ValueType: string; ValueName: "OLLAMA_KEEP_ALIVE"; ValueData: "5m"
Root: HKCU; Subkey: "Environment"; ValueType: string; ValueName: "OLLAMA_CONTEXT_LENGTH"; ValueData: "8192"
Root: HKCU; Subkey: "Environment"; ValueType: string; ValueName: "OLLAMA_FLASH_ATTENTION"; ValueData: "1"
Root: HKCU; Subkey: "Environment"; ValueType: string; ValueName: "OLLAMA_KV_CACHE_TYPE"; ValueData: "q8_0"

[Run]
Filename: "{app}\FRIDAY\FRIDAY.exe"; Description: "{cm:LaunchProgram,F.R.I.D.A.Y.}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM FRIDAY.exe /F"; Flags: runhidden; RunOnceId: "StopFriday"

[Code]
var Failed: String;

function OllamaExe(): String;
begin
  Result := ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe');
  if not FileExists(Result) then Result := '';
end;

procedure Status(const Msg: String);
begin
  WizardForm.StatusLabel.Caption := Msg;
  WizardForm.FilenameLabel.Caption := '';
end;

procedure NoteFail(const What: String);
begin
  if Failed <> '' then Failed := Failed + ', ';
  Failed := Failed + What;
end;

procedure GetOllama();
var Setup: String; Code: Integer;
begin
  if OllamaExe() <> '' then exit;
  Status(CustomMessage('GetOllama'));
  try
    DownloadTemporaryFile('https://ollama.com/download/OllamaSetup.exe', 'OllamaSetup.exe', '', nil);
    Setup := ExpandConstant('{tmp}\OllamaSetup.exe');
    if not Exec(Setup, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
      NoteFail('Ollama');
  except
    NoteFail('Ollama');
  end;
end;

{ Ollama reads its OLLAMA_* variables at start: restart it so the ones above apply, then pull the model }
procedure PullModel();
var Ollama, App: String; Code: Integer;
begin
  Ollama := OllamaExe();
  if Ollama = '' then exit;
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM "ollama app.exe" /F', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM ollama.exe /F', '', SW_HIDE, ewWaitUntilTerminated, Code);
  App := ExtractFilePath(Ollama) + 'ollama app.exe';
  if FileExists(App) then Exec(App, '', '', SW_HIDE, ewNoWait, Code)
  else Exec(Ollama, 'serve', '', SW_HIDE, ewNoWait, Code);
  Sleep(4000);
  Status(CustomMessage('PullModel'));
  if not Exec(Ollama, 'pull qwen3.5:4b', '', SW_SHOWNORMAL, ewWaitUntilTerminated, Code) or (Code <> 0) then
    NoteFail('qwen3.5:4b');
end;

procedure Prefetch();
var Code: Integer;
begin
  Status(CustomMessage('Prefetch'));
  if not Exec(ExpandConstant('{app}\FRIDAY\FRIDAY.exe'), '--prefetch', ExpandConstant('{app}\FRIDAY'), SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
    NoteFail('Whisper');
end;

{ No NVIDIA GPU: Whisper on the CPU (FRIDAY_WHISPER_DEVICE=cpu) }
procedure CheckGpu();
var Code: Integer;
begin
  if not Exec(ExpandConstant('{sys}\nvidia-smi.exe'), '-L', '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
  begin
    RegWriteStringValue(HKCU, 'Environment', 'FRIDAY_WHISPER_DEVICE', 'cpu');
    if not WizardSilent() then MsgBox(CustomMessage('NoNvidia'), mbInformation, MB_OK);
  end;
end;

{ §87 cua-driver: the bundled (reviewed) install.ps1, pinned to the tested release, no logon task, telemetry off }
procedure GetCua();
var Ps, Exe: String; Code: Integer;
begin
  Status(CustomMessage('GetCua'));
  Exe := ExpandConstant('{localappdata}\Programs\Cua\cua-driverin\cua-driver.exe');
  Ps := '$env:CUA_DRIVER_RS_TELEMETRY_ENABLED=''false''; $env:DO_NOT_TRACK=''1''; $env:CUA_DRIVER_RS_VERSION=''0.37.0''; ' +
        '& ''' + ExpandConstant('{tmp}\cua\install.ps1') + ''' -NoAutoStart; & ''' + Exe + ''' telemetry disable';
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell1.0\powershell.exe'),
              '-NoProfile -ExecutionPolicy Bypass -Command "' + Ps + '"', '', SW_HIDE, ewWaitUntilTerminated, Code)
     or not FileExists(Exe) then
    NoteFail('cua-driver');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    CheckGpu();
    GetOllama();
    PullModel();
    Prefetch();
    if WizardIsTaskSelected('cuadriver') then GetCua();
    if (Failed <> '') and not WizardSilent() then
      MsgBox(FmtMessage(CustomMessage('NetFail'), [Failed]), mbError, MB_OK);
  end;
end;
