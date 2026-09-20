"""Import du livre « La chèvre de ma mère » (Ricardo Kaniama) dans MongoDB.

Lit le texte extrait du PDF (/tmp/chevre.txt), le découpe selon les
7 parties + introduction + conclusion du sommaire réel, nettoie la
mise en page (sauts, césures, en-têtes/pieds de page) et insère :
- 1 document dans la collection `livres` (id `la-chevre-de-ma-mere`)
- 9 documents dans la collection `chapitres` (publics)

Idempotent : ré-exécuter remplace le contenu existant.

Usage, depuis /home/bonheur/Downloads/racine/voix_africaine :
    env/bin/python scripts/import_chevre.py
"""

import re
import sys
from pathlib import Path

from pymongo import MongoClient

TXT = Path("/tmp/chevre.txt")
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "voix_africaine"
ADMIN_EMAIL = "admin@voixafricaine.com"

LIVRE_ID = "la-chevre-de-ma-mere"

# (ligne_debut_1based, ligne_fin_exclue, numero, titre) — repères relevés
# dans le texte extrait du PDF (titres des parties + intro + conclusion).
DECOUPAGE = [
    (181, 346, 1, "Introduction"),
    (346, 967, 2, "Première partie : La chèvre de ma mère"),
    (967, 1604, 3, "Deuxième partie : Les escaliers vers la richesse"),
    (1604, 2814, 4, "Troisième partie : Construire et augmenter son fonds"),
    (2814, 3417, 5, "Quatrième partie : Développer l'art de maîtriser les dépenses"),
    (3417, 4006, 6, "Cinquième partie : Opérer le miracle de la prospérité"),
    (4006, 4996, 7, "Sixième partie : Investir en biens des valeurs"),
    (4996, 5345, 8, "Septième partie : L'intelligence financière selon la chèvre"),
    (5345, 6012, 9, "Conclusion"),
]

DESCRIPTION = (
    "Le secret de la prospérité financière : parti d'un capital de 50 $, "
    "le prix d'une chèvre, Ricardo Kaniama raconte comment l'histoire de "
    "la chèvre de sa mère lui a appris à épargner, construire un capital "
    "et investir pour devenir millionnaire."
)


def nettoyer(lignes: list[str]) -> str:
    texte = "\n".join(lignes)
    # Recoller les césures de fin de ligne : « trou-\nver » -> « trouver »
    texte = re.sub(r"(\w)-\n(\w)", r"\1\2", texte)
    # Sauts de page pdf
    texte = texte.replace("\x0c", "\n")
    propres = []
    for ligne in texte.split("\n"):
        s = re.sub(r"[ \t]+", " ", ligne).strip()
        if not s:
            propres.append("")
            continue
        # Numéro de page isolé
        if re.fullmatch(r"\d{1,3}", s):
            continue
        # En-têtes / pieds de page répétés
        if s in ("La chèvre de ma mère", "Le secret de la prospérité financière"):
            continue
        if re.fullmatch(r"[•·\s]*", s):
            continue
        propres.append(s)
    # Tasser les lignes vides multiples
    condense: list[str] = []
    vide_prec = False
    for ligne in propres:
        if ligne == "":
            if not vide_prec:
                condense.append("")
            vide_prec = True
        else:
            condense.append(ligne)
            vide_prec = False
    return "\n".join(condense).strip()


def main() -> int:
    if not TXT.exists():
        print(f"❌ Fichier introuvable : {TXT} (extraire d'abord le PDF avec pdftotext)")
        return 1
    lignes = TXT.read_text(encoding="utf-8").split("\n")

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    admin = db["users"].find_one({"email": ADMIN_EMAIL})
    if not admin:
        print(f"❌ Admin {ADMIN_EMAIL} introuvable — démarrez l'API une fois d'abord.")
        return 1
    created_by = str(admin["_id"])

    # --- Livre (upsert) ---
    db["livres"].update_one(
        {"id": LIVRE_ID},
        {"$set": {
            "id": LIVRE_ID,
            "titre": "La chèvre de ma mère",
            "auteur": "Ricardo Kaniama",
            "description": DESCRIPTION,
            "is_public": True,
        }},
        upsert=True,
    )
    print(f"✅ Livre « La chèvre de ma mère » ({LIVRE_ID}) créé/mis à jour (public)")

    # --- Chapitres (remplacement idempotent) ---
    for debut, fin, numero, titre in DECOUPAGE:
        contenu = nettoyer(lignes[debut - 1: fin - 1])
        chapitre_id = f"{LIVRE_ID}-ch{numero:02d}"
        db["chapitres"].update_one(
            {"id": chapitre_id},
            {"$set": {
                "id": chapitre_id,
                "livre_id": LIVRE_ID,
                "titre": titre,
                "numero": numero,
                "contenu_texte": contenu,
                "audio_url": None,
                "is_public": True,
                "duration_sec": None,
                "created_by": created_by,
                "audio_validated": False,
                "audio_validated_at": None,
                "audio_validated_by": None,
                "audio_public_id": None,
                "audio_resource_type": None,
            }},
            upsert=True,
        )
        print(f"✅ Chapitre {numero}/9 : {titre} ({len(contenu)} caractères)")

    total = db["chapitres"].count_documents({"livre_id": LIVRE_ID})
    print(f"🎉 Terminé : 1 livre + {total} chapitres publics en base.")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
