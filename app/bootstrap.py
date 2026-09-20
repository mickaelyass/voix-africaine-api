"""
Amorçage de la base MongoDB.

Deux opérations **idempotentes**, appelées automatiquement au démarrage
de l'API (voir `main.py`) et disponibles en ligne de commande via
`scripts/init_db.py` :

- `ensure_indexes()`        : crée les index d'unicité et de performance ;
- `ensure_default_admin()`  : crée le compte administrateur par défaut
  s'il n'existe pas encore.

Rien n'est écrasé : relancer ces fonctions plusieurs fois est sans effet
de bord.
"""

from datetime import datetime

from app.auth_utils import get_password_hash
from app.config import settings
from app.database import db


# ==========================================
# INDEX MONGODB
# ==========================================
# (collection, clé(s), options)

INDEXES = [
    ("users", "email", {"unique": True, "name": "uniq_users_email"}),
    ("livres", "id", {"unique": True, "name": "uniq_livres_id"}),
    ("chapitres", "id", {"unique": True, "name": "uniq_chapitres_id"}),
    (
        "chapitres",
        [("livre_id", 1), ("numero", 1)],
        {"unique": True, "name": "uniq_chapitres_livre_numero"},
    ),
    (
        "lectures",
        [("user_id", 1), ("chapitre_id", 1)],
        {"unique": True, "name": "uniq_lectures_user_chapitre"},
    ),
    (
        "commentaires",
        [("chapitre_id", 1), ("created_at", -1)],
        {"name": "idx_commentaires_chapitre_date"},
    ),
]


async def ensure_indexes() -> list[str]:
    """
    Crée les index manquants.

    Un index en échec (données existantes non conformes) n'interrompt
    pas le démarrage : l'erreur est signalée puis ignorée.
    """

    ensured = []

    for collection, keys, options in INDEXES:

        try:
            name = await db[collection].create_index(keys, **options)
            ensured.append(f"{collection}.{name}")

        except Exception as e:
            print(
                f"⚠️  Index {options.get('name')} non créé "
                f"({collection}) : {e}"
            )

    if ensured:
        print(f"✅ {len(ensured)} index MongoDB garantis : {', '.join(ensured)}")

    return ensured


async def ensure_default_admin() -> dict | None:
    """
    Crée le compte administrateur par défaut s'il n'existe pas.

    Retourne le document créé, ou `None` si le compte existait déjà
    (dans ce cas le mot de passe existant n'est jamais écrasé).
    """

    email = settings.DEFAULT_ADMIN_EMAIL

    if await db["users"].find_one({"email": email}):
        print(f"ℹ️  Admin par défaut déjà présent ({email}) — rien à faire")
        return None

    user = {
        "email": email,
        "full_name": settings.DEFAULT_ADMIN_FULL_NAME,
        "hashed_password": get_password_hash(settings.DEFAULT_ADMIN_PASSWORD),
        "disabled": False,
        "role": "admin",
        "created_at": datetime.utcnow(),
    }

    result = await db["users"].insert_one(user)

    print("=" * 62)
    print("✅ ADMIN PAR DÉFAUT CRÉÉ")
    print(f"   email        : {email}")
    print(f"   mot de passe : {settings.DEFAULT_ADMIN_PASSWORD}")
    print("   rôle         : admin")
    print(f"   id           : {result.inserted_id}")
    print("   ⚠️  Changez ce mot de passe après la première connexion.")
    print("=" * 62)

    return user


async def init_database() -> None:
    """Point d'entrée unique : index puis admin par défaut."""

    await ensure_indexes()
    await ensure_default_admin()