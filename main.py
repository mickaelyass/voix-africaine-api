from contextlib import asynccontextmanager
import logging
import json
import sys
from datetime import datetime, timezone

from fastapi import FastAPI, APIRouter

from app.cloudinary_config import init_cloudinary
from app.routes import auth, livres, chapitres, lectures, comment
from app.database import init_db
from app.bootstrap import init_database
from app.middleware import add_middleware
from app.config import settings


# ==========================================
# LOGGING STRUCTURÉ (JSON)
# ==========================================
# Format JSON en production pour ingestion par un outil (Loki, ELK, Grafana).
# Format texte en dev local pour la lisibilité.

class JSONFormatter(logging.Formatter):
    """Formateur JSON structuré pour les logs de production."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Ajouter les extras (ip, duration_ms, etc.)
        for key in ("ip", "path", "method", "status_code", "duration_ms",
                     "username", "user_agent", "db_name", "error",
                     "max_pool_size", "min_pool_size"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging():
    """Configure le logging au démarrage de l'application."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # Nettoyer les handlers existants
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    if settings.LOG_FORMAT.lower() == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        ))

    root_logger.addHandler(handler)

    # Réduire le bruit de certains loggers tiers
    for noisy_logger in ("uvicorn.access", "uvicorn.error", "motor"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    logging.getLogger("voix_africaine").info(
        "logging_initialized",
        extra={"log_level": settings.LOG_LEVEL, "log_format": settings.LOG_FORMAT},
    )


# Initialisation du logging
setup_logging()

logger = logging.getLogger("voix_africaine")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise les connexions au demarrage (remplace on_event deprecie)."""
    # Echec EXPLICITE si un secret Render manque (au runtime, jamais au build).
    settings.require_runtime_settings()
    init_cloudinary()
    await init_db()
    await init_database()

    logger.info(
        "application_started",
        extra={
            "db_name": settings.MONGO_DB_NAME,
            "rate_limit_enabled": settings.RATE_LIMIT_ENABLED,
            "max_pool_size": settings.MONGO_MAX_POOL_SIZE,
        },
    )

    yield

    logger.info("application_stopped")


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
