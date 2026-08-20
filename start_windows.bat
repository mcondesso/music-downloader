@echo off
cd /d "%~dp0"

rem Usa o poetry do PATH se existir; senao, tenta o local de instalacao habitual
where poetry >nul 2>nul
if %errorlevel%==0 (
    poetry run streamlit run app.py
) else if exist "%APPDATA%\Python\Scripts\poetry.exe" (
    "%APPDATA%\Python\Scripts\poetry.exe" run streamlit run app.py
) else (
    echo ERRO: poetry nao encontrado. Instala o Poetry primeiro.
)

pause
