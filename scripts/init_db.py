"""
Initialisation manuelle de la base MongoDB.

À utiliser pour préparer la base sans démarrer l'API
(index + administrateur par défaut).

Usage, depuis la racine du projet :

    env/bin/python -m scripts.init_db
"""

import asyncio
import sys

from app.bootstrap import init_database
from app.database import client, init_db


async def main() -> int:

    await init_db()
    await init_database()

    client.close()

    print("✅ Base de données initialisée")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))