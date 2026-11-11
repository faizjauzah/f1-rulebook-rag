import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.routes import router
from app.config import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="F1 Rulebook RAG",
    description="Retrieval Augmented Generation system for FIA 2026 F1 Regulations",
    version="1.0.0"
)

# Include API routes
app.include_router(router)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Root endpoint serves the UI
@app.get("/")
async def root():
    return FileResponse("app/static/index.html")


@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting F1 Rulebook RAG API (local inference only)")
    logger.info(f"Embedding model: {config.embedding_model} @ {config.embedding_base_url}")
    logger.info(f"LLM: {config.llm_model} @ {config.llm_base_url}")
    logger.info(f"Collection: {config.collection_name}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
