@echo off
setlocal enabledelayedexpansion

REM === Настройки ===
set PYTHON_VERSION=3.12.6
set PYTHON_INSTALLER=python-%PYTHON_VERSION%-amd64.exe
set PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/%PYTHON_INSTALLER%
set GIT_INSTALLER=Git-2.46.0-64-bit.exe
set GIT_URL=https://github.com/git-for-windows/git/releases/download/v2.46.0.windows.1/%GIT_INSTALLER%
set PROJECT_URL=https://github.com/USERNAME/REPO/archive/refs/heads/main.zip
set PROJECT_ZIP=project.zip
set PROJECT_DIR=project

echo ===============================================
echo    🚀 УСТАНОВКА ОКРУЖЕНИЯ ДЛЯ ПРОЕКТА
echo ===============================================

REM --- Проверка прав ---
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ❌ Запусти этот файл от имени администратора.
    pause
    exit /b 1
)

REM --- Проверяем Python ---
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo -----------------------------------------------
    echo ⬇️  Скачиваю Python %PYTHON_VERSION%...
    curl -L -o %PYTHON_INSTALLER% %PYTHON_URL%
    echo Устанавливаю Python...
    start /wait %PYTHON_INSTALLER% /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_test=0
) else (
    echo ✅ Python уже установлен
)

REM --- Проверяем Git ---
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo -----------------------------------------------
    echo ⬇️  Скачиваю Git...
    curl -L -o %GIT_INSTALLER% %GIT_URL%
    echo Устанавливаю Git...
    start /wait %GIT_INSTALLER% /VERYSILENT /NORESTART
) else (
    echo ✅ Git уже установлен
)

REM --- Скачиваем проект ---
echo -----------------------------------------------
echo ⬇️  Скачиваю проект из GitHub...
if exist %PROJECT_DIR% (
    echo Папка проекта уже существует, пропускаю скачивание.
) else (
    curl -L -o %PROJECT_ZIP% %PROJECT_URL%
    powershell -Command "Expand-Archive -Path '%PROJECT_ZIP%' -DestinationPath '.'"
    for /d %%i in (*REPO*) do rename "%%i" "%PROJECT_DIR%"
)

REM --- Проверяем Python и Git ---
python --version
git --version

echo -----------------------------------------------
echo ✅ Установка завершена!
echo -----------------------------------------------
echo Теперь выполни следующие команды:
echo.
echo    cd %PROJECT_DIR%
echo    pip install -r requirements.txt
echo    python main.py
echo.
pause
