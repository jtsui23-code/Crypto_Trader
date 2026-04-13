@echo off
cd /d "%~dp0"
:: Start the containers in the background
docker compose up -d
:: Open the frontend
start http://localhost:5173
echo.
echo The Crypto Trader Bot is running.
echo Press any key in this window to stop the app and shut down containers...
pause >nul
:: Stop the containers
docker compose down