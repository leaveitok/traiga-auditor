@echo off
REM ============================================================================
REM  _release_stamp.bat  -  called by every ship_*.bat, never run directly.
REM
REM    call _release_stamp.bat "ship_something.bat" "one-line summary of the change"
REM
REM  Bumps VERSION (01.7 -> 01.8), appends a row to RELEASES.md, and leaves the new
REM  number in %RELEASE% for the caller to put in the commit trailer and in FILES.
REM
REM  WHY THIS EXISTS. A release record you have to remember to write is a release
REM  record that will be wrong. This runs as part of the ship itself, so the log and
REM  the code are committed together and cannot disagree.
REM
REM  DELIBERATELY NO SETLOCAL. Variables set here must survive back into the calling
REM  bat's scope - that is how %RELEASE% is handed back. Do not add setlocal.
REM
REM  LEADING-ZERO TRAP: cmd's set /a reads 08 and 09 as OCTAL and errors. MAJOR is
REM  "01" and is only ever treated as a STRING - never arithmetic. Only MINOR is
REM  incremented, and it never carries a leading zero. Do not "helpfully" pad it.
REM ============================================================================

set STAMP_BAT=%~1
set STAMP_MSG=%~2

if "%STAMP_BAT%"=="" ( echo   _release_stamp: missing bat name & exit /b 1 )
if "%STAMP_MSG%"=="" ( echo   _release_stamp: missing summary & exit /b 1 )
if not exist "VERSION" ( echo   _release_stamp: VERSION file not found & exit /b 1 )
if not exist "RELEASES.md" ( echo   _release_stamp: RELEASES.md not found & exit /b 1 )

REM -- read current MAJOR.MINOR ------------------------------------------------
set RELEASE_OLD=
for /f "usebackq tokens=1,2 delims=." %%a in ("VERSION") do (
    set RELEASE_MAJ=%%a
    set RELEASE_MIN=%%b
)
if "%RELEASE_MAJ%"=="" ( echo   _release_stamp: VERSION unreadable & exit /b 1 )
if "%RELEASE_MIN%"=="" ( echo   _release_stamp: VERSION unreadable & exit /b 1 )
set RELEASE_OLD=%RELEASE_MAJ%.%RELEASE_MIN%

REM -- bump MINOR only --------------------------------------------------------
set /a RELEASE_NEXT=%RELEASE_MIN%+1
REM set /a does not set a trustworthy errorlevel on success - check the VALUE.
if "%RELEASE_NEXT%"=="" ( echo   _release_stamp: could not increment minor & exit /b 1 )
set RELEASE=%RELEASE_MAJ%.%RELEASE_NEXT%

REM -- UTC date, locale-independent -------------------------------------------
REM %DATE% is formatted per the machine's locale, so it is unusable in a log meant
REM to be read by other people. PowerShell gives a stable ISO date.
for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "(Get-Date).ToUniversalTime().ToString('yyyy-MM-dd')"`) do set RELEASE_DATE=%%d
if "%RELEASE_DATE%"=="" ( echo   _release_stamp: could not read date & exit /b 1 )

REM -- write the new VERSION --------------------------------------------------
REM REDIRECT-FIRST, deliberately. "echo %RELEASE%> VERSION" looks correct but the
REM release number ends in a DIGIT, and cmd reads a digit immediately before > as a
REM stream handle - so 01.1> silently becomes "redirect stream 1", writing "01." to
REM the file. Putting the redirect first removes the ambiguity entirely.
>"VERSION" echo %RELEASE%

REM -- append the row. RELEASES.md is append-only; the table is the last thing in
REM    the file precisely so a row can be added without rewriting anything above it.
>>"RELEASES.md" echo ^| %RELEASE% ^| %RELEASE_DATE% ^| %STAMP_BAT% ^| %STAMP_MSG% ^|

echo   Release %RELEASE_OLD% -^> %RELEASE%  (%STAMP_BAT%)
exit /b 0
