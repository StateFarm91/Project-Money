import env  # noqa: F401
import uvicorn
from brambleloop.app import main
uvicorn.run(main.app, host="127.0.0.1", port=8899, log_level="warning")
