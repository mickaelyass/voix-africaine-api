from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, APIRouter

from app.cloudinary_config import init_cloudinary
from app.routes import auth, livres, chapitres, lectures, comment
from app.database import init_db
from app.bootstrap import init_database
from app.middleware import add_middleware
from app.config import settings

logger = logging.getLogger("voix_africaine")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise les connexions au demarrage (remplace on_event deprecie)."""
    # Echec EXPLICITE si un secret Render manque (au runtime, jamais au build).
    settings.require_runtime_settings()
    init_cloudinary()
    await init_db()
    await init_database()
    yield

app = FastAPI(
    title="API de Gestion de Livres",
    description="API pour la gestion de livres, chapitres et lectures",
    version="1.0.0",
    docs_url="/docs",  # Active la documentation Swagger a /docs
    redoc_url="/redoc",  # Active la documentation Redoc a /redoc
    openapi_url="/openapi.json",  # URL pour le schema OpenAPI
    lifespan=lifespan,
)


@app.get("/health", tags=["Health"])
async def health():
    """Sonde utilisee par Render (healthCheckPath) : ne touche ni DB ni secrets."""
    return {"status": "ok"}


# Inclusion des routeurs avec des prefixes et tags pour une meilleure organisation
app.include_router(auth.router)
app.include_router(livres.router)
app.include_router(chapitres.router)
app.include_router(lectures.router)
app.include_router(comment.router)

# Configuration des middlewares
add_middleware(app)
