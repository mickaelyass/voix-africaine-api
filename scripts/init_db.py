"""
Initialisation manuelle de la base MongoDB.

A utiliser pour preparer la base sans demarrer l'API
(index + administrateur par defaut).

Usage, depuis la racine du projet :

    env/bin/python -m scripts.init_db
"""

import asyncio
import sys

from app.bootstrap import init_database
from app.database import get_client, init_db


async def main() -> int:

    await init_db()
    await init_database()

    get_client().close()

    print("Base de donnees initialisee")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
