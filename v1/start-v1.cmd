@echo off
start "Puzzle V1 Web" cmd /k "cd /d C:\Users\admin\Downloads\puzzle && node serve-v1-local.mjs"
start "Puzzle V1 Bridge" cmd /k "cd /d C:\Users\admin\Downloads\puzzle\v1\node-bridge && node server.mjs"
echo Puzzle V1 services are starting...
echo Page:   http://127.0.0.1:8000/v1/index.html
echo Bridge: http://127.0.0.1:3210/health
