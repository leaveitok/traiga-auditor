@echo off
REM ============================================================================
REM  _verify_commit.bat  -  called by every ship_*.bat AFTER git commit.
REM
REM    call _verify_commit.bat
REM    if errorlevel 1 goto :verifyfail
REM
REM  Confirms THE FILES THIS COMMIT TOUCHED match what is on disk. errorlevel 1 if not.
REM
REM  SCOPE - the whole point, and the thing this got wrong twice.
REM  Release 01.3 blocked its own push because the check ran `git diff HEAD` across the
REM  ENTIRE working tree and tripped on update-user-guide.skill, a file that had been
REM  modified for hours and had nothing to do with the commit. A guard that fires on
REM  unrelated dirt is a guard people learn to ignore, which is worse than no guard.
REM  It now iterates ONLY the paths in HEAD.
REM
REM  HISTORY OF THIS CHECK - three defects, all fixed here:
REM   1. (01.2) Set BAD=1 inside a for-block and tested "!BAD!"=="1" after it. The flag
REM      did not survive the block, so the guard printed MISMATCH and pushed anyway. It
REM      had been DECORATIVE in every bat that used it. No flag variable is used now -
REM      a marker FILE records failures, which no expansion quirk can defeat.
REM   2. (01.2) fc /b byte-compares, but Git for Windows commits with autocrlf so the blob
REM      holds LF while the working file keeps CRLF. Every cmd-written file (VERSION,
REM      RELEASES.md) therefore always "mismatched". git diff understands normalisation.
REM   3. (01.3) Unscoped - see above.
REM
REM  HONEST LIMIT - READ THIS. This cannot detect a file that was ALREADY truncated when
REM  it was staged: git would faithfully commit the truncated bytes and the working tree
REM  would agree with them. What actually protects against NTFS truncation is verifying
REM  each file byte-for-byte at WRITE time, before this bat ever runs. A pass here means
REM  "the commit matches the disk", NOT "the content is correct".
REM ============================================================================

set VC_MARK=%TEMP%\traiga_verify_fail.txt
if exist "%VC_MARK%" del /f /q "%VC_MARK%"

git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 (
    echo   _verify_commit: cannot read HEAD
    exit /b 1
)

git show --pretty="" --name-only HEAD > "%TEMP%\traiga_commit_files.txt" 2>nul
if errorlevel 1 (
    echo   _verify_commit: cannot list the commit's files
    exit /b 1
)

REM Compare ONLY the paths this commit touched. Per-file so the failing name is reported,
REM and via git diff so line-ending normalisation is handled the way git handles it.
REM A deleted/renamed-away path is skipped rather than reported: it is legitimately absent.
for /f "usebackq delims=" %%F in ("%TEMP%\traiga_commit_files.txt") do (
    if exist "%%F" (
        git diff --quiet HEAD -- "%%F"
        if errorlevel 1 echo %%F>> "%VC_MARK%"
    )
)

if exist "%VC_MARK%" goto :differs

echo   Commit matches the working tree.
exit /b 0

:differs
echo.
echo   *** These committed files do NOT match what is on disk: ***
type "%VC_MARK%"
echo.
git --no-pager diff --stat HEAD -- @"%TEMP%\traiga_commit_files.txt" 2>nul
echo   Nothing has been pushed. Investigate before shipping.
exit /b 1
