@echo off
:: Check if Docker engine is responsive
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not running. 
    echo Please launch Docker Desktop and wait for it to start.
    pause
    exit /b
)

cd /d "%~dp0"
:: Attempt to start containers
docker compose up -d
if %errorlevel% neq 0 (
    echo [ERROR] Failed to start containers. Check your docker-compose.yml or logs.
    pause
    exit /b
)

:: Open the frontend
start http://localhost:5173
echo.
echo The Crypto Trader Bot is running.
echo Press any key in this window to stop the app and shut down containers...
pause >nul

:: Stop the containers gracefully
docker compose down