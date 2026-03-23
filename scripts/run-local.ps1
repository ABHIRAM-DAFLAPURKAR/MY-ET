# Run My ET stack on localhost (no Docker).
# Prerequisites: MongoDB listening on 127.0.0.1:27017, Java 17+, Python 3.10+, Node 20+
#
# Open FOUR terminals from repo root and run each block in order.

$root = Split-Path -Parent $PSScriptRoot
Write-Host ""
Write-Host "=== My ET — localhost (no Docker) ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "1) MongoDB — must be running (e.g. Windows service or: mongod --dbpath ...)" -ForegroundColor Yellow
Write-Host ""
Write-Host "2) AI brain (terminal 1):" -ForegroundColor Green
Write-Host "   cd `"$root\ai-brain-service`""
Write-Host "   python -m venv venv"
Write-Host "   .\venv\Scripts\Activate.ps1"
Write-Host "   pip install -r requirements.txt"
Write-Host "   python run.py"
Write-Host "   -> http://127.0.0.1:5005/health"
Write-Host ""
Write-Host "3) Spring API (terminal 2):" -ForegroundColor Green
Write-Host "   cd `"$root\abs`""
Write-Host "   mvn -q spring-boot:run"
Write-Host "   (Uses application.yaml defaults: Mongo + AI brain on 127.0.0.1)"
Write-Host "   -> http://127.0.0.1:8080/news/"
Write-Host ""
Write-Host "4) Next.js (terminal 3):" -ForegroundColor Green
Write-Host "   cd `"$root\frontend`""
Write-Host "   npm install"
Write-Host "   npm run dev"
Write-Host "   -> http://localhost:3000"
Write-Host ""
Write-Host "Optional: copy frontend\.env.local.example to frontend\.env.local if you change ports." -ForegroundColor DarkGray
Write-Host ""
