@echo off
cd /d C:\WSL\NemoClaw\npu-server
for /f "tokens=1,2 delims==" %%a in (.env) do (
    if not "%%a"=="" if not "%%a:~0,1%"=="#" set "%%a=%%b"
)
C:\Users\joech\AppData\Local\Programs\Python\Python311\python.exe server.py
