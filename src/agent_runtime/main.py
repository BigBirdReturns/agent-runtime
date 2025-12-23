from fastapi import FastAPI
from agent_runtime.api import router as api_router

app = FastAPI(title="Agent Runtime", version="0.2.0")
app.include_router(api_router, prefix="/v1")
