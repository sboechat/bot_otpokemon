@echo off
setlocal
cd /d "%~dp0"

set "LOG=%~dp0criar_exe.log"
set "TEMP_LOG=%TEMP%\bot_loot_pip_%RANDOM%.log"
set "PY="
echo Registro da criacao do bot_loot.exe > "%LOG%"
echo Iniciando criacao do bot_loot.exe...

python --version >nul 2>>"%LOG%"
if not errorlevel 1 (
    set "PY=python"
) else (
    echo O comando python nao funcionou. Tentando py -3...
    py -3 --version >nul 2>>"%LOG%"
    if errorlevel 1 (
        echo ERRO: Python 3 nao foi encontrado. Instale o Python 3.12 e tente novamente.
        echo ERRO: Python 3 nao foi encontrado. >> "%LOG%"
        goto falha
    )
    set "PY=py -3"
)

echo Usando: %PY%
echo Interpretador: %PY% >> "%LOG%"
call :instalar pyinstaller
if errorlevel 1 goto falha
call :instalar opencv-python
if errorlevel 1 goto falha
call :instalar numpy
if errorlevel 1 goto falha
call :instalar pywin32
if errorlevel 1 goto falha
call :instalar keyboard
if errorlevel 1 goto falha

echo.
echo Gerando o executavel...
echo Comando: %PY% -m PyInstaller --onefile --noconsole --clean --name bot_loot bot_loot.py >> "%LOG%"
%PY% -m PyInstaller --onefile --noconsole --clean --name bot_loot --distpath "%~dp0dist" --workpath "%~dp0build" --specpath "%TEMP%" "%~dp0bot_loot.py" > "%TEMP_LOG%" 2>&1
set "RESULTADO=%ERRORLEVEL%"
type "%TEMP_LOG%"
type "%TEMP_LOG%" >> "%LOG%"
if not "%RESULTADO%"=="0" (
    echo ERRO: PyInstaller falhou. Consulte o erro acima e o arquivo "%LOG%".
    goto falha
)

if not exist "%~dp0dist\bot_loot.exe" (
    echo ERRO: PyInstaller terminou sem gerar dist\bot_loot.exe.
    echo ERRO: Executavel nao encontrado em dist. >> "%LOG%"
    goto falha
)
copy /Y "%~dp0dist\bot_loot.exe" "%~dp0bot_loot.exe" >nul
if errorlevel 1 (
    echo ERRO: Nao foi possivel copiar bot_loot.exe para esta pasta.
    echo ERRO: Falha ao copiar o executavel. >> "%LOG%"
    goto falha
)

del "%TEMP_LOG%" >nul 2>&1
echo.
echo Sucesso! Executavel criado em:
echo %~dp0bot_loot.exe
echo Registro completo: %LOG%
pause
exit /b 0

:instalar
echo.
echo Instalando %~1...
echo Instalando %~1... >> "%LOG%"
%PY% -m pip install %~1 > "%TEMP_LOG%" 2>&1
set "RESULTADO=%ERRORLEVEL%"
type "%TEMP_LOG%"
type "%TEMP_LOG%" >> "%LOG%"
if not "%RESULTADO%"=="0" (
    echo ERRO: A instalacao de %~1 falhou. O erro real do pip esta acima e em "%LOG%".
    echo ERRO: A instalacao de %~1 falhou. >> "%LOG%"
    exit /b 1
)
echo %~1 instalado com sucesso.
exit /b 0

:falha
if exist "%TEMP_LOG%" del "%TEMP_LOG%" >nul 2>&1
echo.
echo A criacao do executavel falhou. Consulte "%LOG%" para ver os detalhes.
pause
exit /b 1
