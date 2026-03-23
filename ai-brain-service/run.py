from pathlib import Path

from dotenv import load_dotenv

# Local dev: env in ai-brain-service/.env or ai-brain-service/app/.env
_root = Path(__file__).resolve().parent
load_dotenv(_root / ".env")
load_dotenv(_root / "app" / ".env", override=True)

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005)