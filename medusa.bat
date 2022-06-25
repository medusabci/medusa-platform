::[Bat To Exe Converter]
::
::YAwzoRdxOk+EWAjk
::fBw5plQjdCmDJFSB8FcjKVZRVAG+MW6+E6Ydpfj37v6BrV8QGecnfbPS2buAHOkQ5UuqfJUitg==
::YAwzuBVtJxjWCl3EqQJgSA==
::ZR4luwNxJguZRRnk
::Yhs/ulQjdF+5
::cxAkpRVqdFKZSzk=
::cBs/ulQjdF+5
::ZR41oxFsdFKZSDk=
::eBoioBt6dFKZSDk=
::cRo6pxp7LAbNWATEpCI=
::egkzugNsPRvcWATEpCI=
::dAsiuh18IRvcCxnZtBJQ
::cRYluBh/LU+EWAnk
::YxY4rhs+aU+JeA==
::cxY6rQJ7JhzQF1fEqQJQ
::ZQ05rAF9IBncCkqN+0xwdVs0
::ZQ05rAF9IAHYFVzEqQJQ
::eg0/rx1wNQPfEVWB+kM9LVsJDGQ=
::fBEirQZwNQPfEVWB+kM9LVsJDGQ=
::cRolqwZ3JBvQF1fEqQJQ
::dhA7uBVwLU+EWDk=
::YQ03rBFzNR3SWATElA==
::dhAmsQZ3MwfNWATElA==
::ZQ0/vhVqMQ3MEVWAtB9wSA==
::Zg8zqx1/OA3MEVWAtB9wSA==
::dhA7pRFwIByZRRnk
::Zh4grVQjdCmDJFSB8FcjKVZRVAG+MW6+E6Ydpfj37v6BrV8QGecnfbPW37CbM+Fd713hFQ==
::YB416Ek+ZG8=
::
::
::978f952a14a936cc963da21a135fa983
:: ===========================================================================================================================
:: Activate environment and execute main.py
call "venv\Scripts\activate"
IF %ERRORLEVEL% NEQ 0 GOTO activateError
:: Change directory to src
cd "src"
IF %ERRORLEVEL% NEQ 0 GOTO cdError
:: Execute main-py
python "main.py"
IF %ERRORLEVEL% NEQ 0 GOTO pythonError
::PAUSE
exit /b 1

:activateError
powershell -Command "& {Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('Python venv cant be activated!', 'Error', 'OK', [System.Windows.Forms.MessageBoxIcon]::Error);}"
echo %ERRORLEVEL%
::PAUSE
exit /b 1

:cdError
powershell -Command "& {Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('Directory src not found!', 'Error', 'OK', [System.Windows.Forms.MessageBoxIcon]::Error);}"
echo %ERRORLEVEL%
::PAUSE
exit /b 1

:pythonError
powershell -Command "& {Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('MEDUSA cannot be executed!. Executing as administrator might help', 'Error', 'OK', [System.Windows.Forms.MessageBoxIcon]::Error);}"
echo %ERRORLEVEL%
::PAUSE
exit /b 1


:: ===========================================================================================================================

:: ===========================================================================================================================
:: HOW TO COMPILE THIS FILE WITH WINDOWS IEXPRESS TOOL
:: 	- Right-click it an Run as administrator.
:: 	- Create a new SED and select "Extract files and run an installation command."
:: 	- Package title: medusa
:: 	- Confirmation prompt: no prompt
:: 	- License agreement: no license
:: 	- Packaged files: add the script you want
:: 	- Install program: cmd /c medusa.bat
:: 	- Show window: hidden.
:: 	- Finished message: no message
:: 	- Package name and options: medusa, hide file extracting process
:: 	- Restart: no restart
:: 	- Save SED file: update SED file in main repository of medusa-platform
:: 	- Click next and you should have your .exe!
:: ===========================================================================================================================