import uvicorn
from app import app
from app.config import CONFIG

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=CONFIG['PORT'])