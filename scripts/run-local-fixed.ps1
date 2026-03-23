# Fixed localhost runner - NO DOCKER
# Run in PowerShell from project root

Write-Host "`n=== News AI Service - Localhost Setup (No Docker) ===`n" -ForegroundColor Cyan
Write-Host "1. MongoDB: Already running on 27017 ✓" -ForegroundColor Green
Write-Host "2. Spring ABS API: Already on 8080 ✓" -ForegroundColor Green
Write-Host "3. AI Brain MISSING on 5005 - STARTING NOW..." -ForegroundColor Yellow

# Start AI Brain in background (detached)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd ai-brain-service; python -m venv venv; .\venv\Scripts\Activate.ps1; pip install -r requirements.txt; python run.py" -WindowStyle Minimized

Write-Host "`n4. Frontend setup..." -ForegroundColor Cyan
Set-Location frontend
if (!(Test-Path .env.local)) { Copy-Item .env.local.example .env.local }
npm install
npm run dev

Write-Host "`n✅ Full stack: http://localhost:3000`nAI Brain: http://127.0.0.1:5005/health`nAPI: http://127.0.0.1:8080/news/`n" -ForegroundColor Green
