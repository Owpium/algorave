@echo off
rem t2s.bat - audio -> Strudel + samples + rendu + verdict PASS/FAIL (aucun LLM).
rem   tools\t2s.bat "refs\morceau.mp3" --start 97.1 --dur 60
rem   tools\t2s.bat "refs\morceau.mp3" --auto-excerpt --slug morceau
rem   glisser-deposer un fichier audio sur ce .bat = --auto-excerpt (fenetre gardee ouverte a la fin)
rem   tools\t2s.bat golden   = tools\check_golden.py (non-regression des 5 refs)
setlocal
set "ROOT=%~dp0.."
set "PATH=%LOCALAPPDATA%\nodejs;%PATH%"
call "%ROOT%\.venv\Scripts\activate.bat"
cd /d "%ROOT%"
if "%~1"=="" (
  set /p "AUDIO=Fichier audio (glisser ici puis Entree) : "
  call python tools\t2s.py %%AUDIO%% --auto-excerpt
  pause
  exit /b
)
if /i "%~1"=="golden" (
  python tools\check_golden.py %2 %3 %4 %5 %6 %7 %8 %9
  exit /b
)
if "%~2"=="" (
  python tools\t2s.py "%~1" --auto-excerpt
  pause
  exit /b
)
python tools\t2s.py %*
