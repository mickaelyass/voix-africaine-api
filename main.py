from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, APIRouter

from app.cloudinary_config import init_cloudinary
from app.routes import auth, livres, chapitres, lectures,comment
from app.database import init_db
from app.bootstrap import init_database
from app.middleware import add_middleware
from app.config import settings

logger = logging.getLogger("voix_africaine")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise les connexions au démarrage (remplace on_event déprécié)."""
    init_cloudinary()
    await init_db()
    await init_database()
    yield

app = FastAPI(
    title="API de Gestion de Livres",
    description="API pour la gestion de livres, chapitres et lectures",
    version="1.0.0",
    docs_url="/docs",  # Active la documentation Swagger à /docs
    redoc_url="/redoc",  # Active la documentation Redoc à /redoc
    openapi_url="/openapi.json",  # URL pour le schéma OpenAPI
    lifespan=lifespan,
)

# Inclusion des routeurs avec des préfixes et tags pour une meilleure organisation
app.include_router(auth.router)
app.include_router(livres.router)
app.include_router(chapitres.router)
app.include_router(lectures.router)
app.include_router(comment.router)

# Configuration des middlewares
add_middleware(app)
