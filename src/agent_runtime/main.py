from fastapi import FastAPI
from agent_runtime.api import router as api_router
from agent_runtime import __version__

app = FastAPI(title="Agent Runtime", version=__version__)
app.include_router(api_router, prefix="/v1")
