import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

logger = logging.getLogger("voix_africaine.db")


# ==========================================
# Connexion MongoDB (lazy - pas de connexion a l'import)
# ==========================================
# `client` / `db` restent importables partout (from app.database import db)
# sans planter le build Render. La vraie connexion est creee dans
# `init_db()` au demarrage, apres `require_runtime_settings()`.
# `db` est un proxy paresseux : les `from app.database import db` existants
# continuent de fonctionner car l'objet proxy reste le meme avant/apres init.

_client: AsyncIOMotorClient | None = None
_real_db: AsyncIOMotorDatabase | None = None


class _LazyDB:
    """Proxy qui transmet les acces vers la vraie base apres init_db()."""

    def _target(self) -> AsyncIOMotorDatabase:
        if _real_db is None:
            raise RuntimeError(
                "MongoDB non initialise - init_db() n'a pas ete appele "
                "(verifiez la variable MONGO)."
            )
        return _real_db

    def __getattr__(self, name):
        return getattr(self._target(), name)

    def __getitem__(self, name):
        return self._target()[name]


client = None  # compatibilite ascendante : utilisez get_client()
db = _LazyDB()


def get_client() -> AsyncIOMotorClient:
    if _client is None:
        raise RuntimeError(
            "MongoDB non initialise - init_db() n'a pas ete appele "
            "(verifiez la variable MONGO)."
        )
    return _client


def get_db() -> AsyncIOMotorDatabase:
    if _real_db is None:
        raise RuntimeError(
            "MongoDB non initialise - init_db() n'a pas ete appele "
            "(verifiez la variable MONGO)."
        )
    return _real_db


async def init_db():
    """Verifie la connexion a MongoDB Atlas avec un pool optimise."""
    global _client, _real_db

    settings.require_runtime_settings()
    assert settings.MONGO is not None  # garanti par require_runtime_settings()

    if _client is None:
        _client = AsyncIOMotorClient(
            settings.MONGO,
            # ==========================================
            # POOL DE CONNEXIONS — réduit la latence des requêtes répétées
            # ==========================================
            maxPoolSize=settings.MONGO_MAX_POOL_SIZE,
            minPoolSize=settings.MONGO_MIN_POOL_SIZE,
            serverSelectionTimeoutMS=settings.MONGO_SERVER_SELECTION_TIMEOUT_MS,
            connectTimeoutMS=settings.MONGO_CONNECT_TIMEOUT_MS,
            socketTimeoutMS=settings.MONGO_SOCKET_TIMEOUT_MS,
        )
        _real_db = _client[settings.MONGO_DB_NAME]
        # expose aussi le vrai client pour le code qui fait `from app.database import client`
        globals()["client"] = _client

    try:
        await _client.admin.command("ping")
        logger.info(
            "mongodb_connected",
            extra={
                "db_name": settings.MONGO_DB_NAME,
                "max_pool_size": settings.MONGO_MAX_POOL_SIZE,
                "min_pool_size": settings.MONGO_MIN_POOL_SIZE,
            },
        )
        print(f"Connecte a MongoDB : {settings.MONGO_DB_NAME}")
    except Exception as e:
        logger.error(
            "mongodb_connection_failed",
            extra={"error": str(e)},
        )
        print(f"Erreur de connexion a MongoDB : {e}")
        raise
