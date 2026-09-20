
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings


# ==========================================
# Connexion MongoDB
# ==========================================

client = AsyncIOMotorClient(settings.MONGO)

db = client[settings.MONGO_DB_NAME]


async def init_db():
    """
    Vérifie la connexion à MongoDB Atlas.
    """

    try:
        await client.admin.command("ping")

        print(
            f"✅ Connecté à MongoDB : {settings.MONGO_DB_NAME}"
        )

    except Exception as e:

        print(
            f"❌ Erreur de connexion à MongoDB : {e}"
        )

        raise

