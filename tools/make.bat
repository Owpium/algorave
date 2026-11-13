@echo off
rem make.bat - cree un morceau (kit de construction + one-shots + moteur de mix Python), aucun LLM.
rem   Marche depuis n'importe quel dossier : le .bat se place tout seul dans le dossier du projet.
rem   En PowerShell, toujours avec le prefixe .\ (ou le chemin complet) :
rem     cd "C:\Users\Jo'\Music\ALGORAVE"
rem     .\tools\make.bat --kit sas131 --key F# --seed 1
rem     .\tools\make.bat --kit sas131 --key G# --seed 1 --n 3
rem     .\tools\make.bat --list-kits
rem     .\tools\make.bat --help
rem   .\tools\make.bat qa "out\make\x\x - 124bpm - 11A.wav" --bpm 124   = tools\make_qa.py (controle seul)
setlocal
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
if not exist "%ROOT%\.venv\Scripts\python.exe" (
  echo [make] .venv introuvable dans "%ROOT%"
  exit /b 1
)
set "PYTHONIOENCODING=utf-8"
if /i "%~1"=="qa" goto :qa
cd /d "%ROOT%"
"%ROOT%\.venv\Scripts\python.exe" tools\make.py %*
exit /b %ERRORLEVEL%

:qa
set "W1=%~2"
if exist "%~f2" set "W1=%~f2"
cd /d "%ROOT%"
"%ROOT%\.venv\Scripts\python.exe" tools\make_qa.py "%W1%" %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%
