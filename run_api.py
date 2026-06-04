"""Convenience entry point — run with: python run_api.py

Starts the FastAPI server on http://127.0.0.1:8000.
OpenAPI docs at http://127.0.0.1:8000/docs.
"""

import uvicorn

from finbar.config.settings import API_HOST, API_PORT
from finbar.startup.api import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host=API_HOST, port=API_PORT)
