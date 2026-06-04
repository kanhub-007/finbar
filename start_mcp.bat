@echo off
cd /d "%~dp0"

echo Starting Finbar MCP Server...
echo MCP  -^> http://localhost:8003

:: Activate virtual environment and run
call .venv\Scripts\activate.bat

:: Force HTTP transport for client connectivity
set FINBAR_TRANSPORT=http
set FINBAR_HOST=127.0.0.1
set FINBAR_PORT=8003

python run_mcp.py

pause
