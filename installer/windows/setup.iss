; ===== Inno Setup script =====
#define AppName "Lab Integrator Service"        ; <— CAMBIA si tu app se llama distinto
#define CompanyName "Vitronix"                ; <— CAMBIA (p.ej. "Axolys")
#define AppVersion "1.0.0"                      ; <— provisional; luego lo inyectamos desde CI
#define ExeName "lab-integrator.exe"            ; <— CAMBIA si tu binario se llama distinto
#define SourceBin "..\\..\\dist\\lab-integrator.exe"    ; <— CAMBIA si tu CI deja el .exe en otra ruta

[Setup]
AppId={{6B1B7D1A-BA73-4D89-9D22-9C1B47E7E6F3}} ; ID estable para upgrades/uninstall
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#CompanyName}
DefaultDirName={autopf}\{#CompanyName}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=..\..\out\installer
OutputBaseFilename={#AppName}-Setup-{#AppVersion}-x64
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
DisableProgramGroupPage=yes
SetupIconFile=installer\windows\lab_integrator_icon.ico

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear icono en el Escritorio"; GroupDescription: "Tareas adicionales:"; Flags: unchecked

[Files]
Source: "{#SourceBin}"; DestDir: "{app}"; DestName: "{#ExeName}"; Flags: ignoreversion
Source: "app\\configs\\*"; DestDir: "{app}\\configs"; Flags: recursesubdirs createallsubdirs ignoreversion skipifsourcedoesntexist
Source: "docs\\*"; DestDir: "{app}\\docs"; Flags: recursesubdirs createallsubdirs ignoreversion skipifsourcedoesntexist
Source: "README*"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "LICENSE*"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#ExeName}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#ExeName}"; Tasks: desktopicon

; Si tu app soporta instalarse como servicio con un parámetro (p.ej. "install"),
; puedes descomentar esta sección para ofrecerlo al final del setup:
; [Run]
; Filename: "{app}\{#ExeName}"; Parameters: "install"; Description: "Instalar como servicio de Windows"; Flags: postinstall nowait runhidden skipifsilent

; [UninstallRun]
; Filename: "{app}\{#ExeName}"; Parameters: "uninstall"; RunOnceId: "UninstallService"; Flags: runhidden
