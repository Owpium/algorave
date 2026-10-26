@echo off
rem t2s.bat - audio -> Strudel + samples + rendu + verdict PASS/FAIL (aucun LLM).
rem   Marche depuis n'importe quel dossier : le .bat se place tout seul dans le dossier du projet.
rem   En PowerShell, toujours avec le prefixe .\ (ou le chemin complet) :
rem     cd "C:\Users\Jo'\Music\ALGORAVE"
rem     .\tools\t2s.bat "refs\morceau.mp3" --start 97.1 --dur 60
rem     .\tools\t2s.bat "refs\morceau.mp3" --auto-excerpt --slug morceau
rem     & "C:\Users\Jo'\Music\ALGORAVE\tools\t2s.bat" "D:\x.wav" --auto-excerpt   (depuis ailleurs)
rem   glisser-deposer un fichier audio sur ce .bat = --auto-excerpt (fenetre gardee ouverte a la fin)
rem   .\tools\t2s.bat golden   = tools\check_golden.py (non-regression des 5 refs)
rem   .\tools\t2s.bat batch "D:\mes wavs" [--prune-stems ...]   = tools\t2s_batch.py (lot de morceaux, reprise auto)
rem Un chemin relatif (fichier / dossier) est d'abord cherche depuis le dossier courant, sinon depuis le projet.
setlocal
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "PATH=%LOCALAPPDATA%\nodejs;%PATH%"
if not exist "%ROOT%\.venv\Scripts\activate.bat" (
  echo [t2s] .venv introuvable dans "%ROOT%"
  exit /b 1
)
call "%ROOT%\.venv\Scripts\activate.bat"
if "%~1"=="" (
  cd /d "%ROOT%"
  set /p "AUDIO=Fichier audio (glisser ici puis Entree) : "
  call python tools\t2s.py %%AUDIO%% --auto-excerpt
  pause
  exit /b
)
if /i "%~1"=="batch" goto :batch
if /i "%~1"=="golden" (
  cd /d "%ROOT%"
  python tools\check_golden.py %2 %3 %4 %5 %6 %7 %8 %9
  exit /b
)
rem audio path: resolved from the caller's folder when it exists there (before the cd)
set "A1=%~1"
if exist "%~f1" set "A1=%~f1"
cd /d "%ROOT%"
if "%~2"=="" (
  python tools\t2s.py "%A1%" --auto-excerpt
  pause
  exit /b
)
shift
set ARGS=
:argloop
if "%~1"=="" goto :argrun
set ARGS=%ARGS% %1
shift
goto :argloop
:argrun
python tools\t2s.py "%A1%" %ARGS%
exit /b

:batch
shift
rem batch folder: resolved from the caller's folder when it exists there
set "B1=%~1"
if exist "%~f1" set "B1=%~f1"
shift
set ARGS=
:batchloop
if "%~1"=="" goto :batchrun
set ARGS=%ARGS% %1
shift
goto :batchloop
:batchrun
cd /d "%ROOT%"
python tools\t2s_batch.py "%B1%" %ARGS%
exit /b
