# === Установка Git и Python с автопоиском пути и обновлением PATH ===
$tempPath = [System.IO.Path]::GetTempPath()

$files = @(
    @{ Url = "https://github.com/git-for-windows/git/releases/latest/download/Git-2.46.0-64-bit.exe"; Path = "$tempPath\git.exe" },
    @{ Url = "https://www.python.org/ftp/python/3.12.6/python-3.12.6-amd64.exe"; Path = "$tempPath\python.exe" }
)

# --- Скачивание установщиков ---
$webClient = New-Object System.Net.WebClient
foreach ($file in $files) {
    if (-not (Test-Path $file.Path)) {
        try { $webClient.DownloadFile($file.Url, $file.Path) } catch {}
    }
}
$webClient.Dispose()

# --- Установка Git ---
Start-Process -Wait -FilePath "$tempPath\git.exe" -ArgumentList "/VERYSILENT","/NORESTART","/ALLUSERS","/COMPONENTS=gitbash,assoc,icons,ext"

# --- Установка Python ---
Start-Process -Wait -FilePath "$tempPath\python.exe" -ArgumentList "/quiet","InstallAllUsers=1","PrependPath=1","Include_pip=1","Include_test=0"

# --- Поиск установленного Git и обновление PATH ---
$gitPaths = @(
    "C:\Program Files\Git\bin",
    "C:\Program Files (x86)\Git\bin",
    "$env:LOCALAPPDATA\Programs\Git\bin",
    "$env:LOCALAPPDATA\Git\bin"
)

$gitFound = $false
foreach ($path in $gitPaths) {
    if (Test-Path "$path\git.exe") {
        $envPathUser = [System.Environment]::GetEnvironmentVariable("Path", "User")
        if ($envPathUser -notmatch [Regex]::Escape($path)) {
            [System.Environment]::SetEnvironmentVariable("Path", $envPathUser + ";" + $path, "User")
        }
        $gitFound = $true
        break
    }
}

if (-not $gitFound) {
    # если не нашли — попробуем найти по всему диску C:
    try {
        $gitExe = Get-ChildItem -Path "C:\" -Filter git.exe -Recurse -ErrorAction SilentlyContinue -Force |
                   Where-Object { $_.FullName -match "\\Git\\bin\\git\.exe$" } |
                   Select-Object -First 1
        if ($gitExe) {
            $gitDir = Split-Path $gitExe.FullName -Parent
            $envPathUser = [System.Environment]::GetEnvironmentVariable("Path", "User")
            [System.Environment]::SetEnvironmentVariable("Path", $envPathUser + ";" + $gitDir, "User")
        }
    } catch {}
}

# --- Обновляем PATH в текущей сессии ---
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
