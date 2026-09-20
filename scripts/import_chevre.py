"""Import du livre « La chèvre de ma mère » (Ricardo Kaniama) dans MongoDB.

Lit le texte extrait du PDF (/tmp/chevre.txt), le découpe selon les
7 parties + introduction + conclusion du sommaire réel, nettoie la
mise en page (sauts, césures, en-têtes/pieds de page) et insère :
- 1 document dans la collection `livres` (id `la-chevre-de-ma-mere`)
- 9 documents dans la collection `chapitres` (publics)

Idempotent : ré-exécuter remplace le contenu existant.

Usage, depuis /home/bonheur/Downloads/racine/voix_africaine :

  # MongoDB local (défaut, lit MONGO dans .env) :
    env/bin/python scripts/import_chevre.py

  # MongoDB Atlas :
    env/bin/python scripts/import_chevre.py --mongo-uri "mongodb+srv://<user>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority"
    # ou :  MONGO="mongodb+srv://..." env/bin/python scripts/import_chevre.py
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from pymongo import MongoClient

TXT_CANDIDATS = [
    Path("/tmp/chevre.txt"),
    Path(__file__).resolve().parent.parent.parent / "chevre.txt",
    Path("/tmp/chevre_utf8.txt"),
]
PDF_DEFAUT = Path("/home/bonheur/Downloads/racine/la chèvre de ma mère .pdf")

# --- Connexion MongoDB : Atlas OU local ---
# Priorité : 1) --mongo-uri en CLI  2) variable MONGO (.env / environnement)  3) localhost
# Exemple Atlas : mongodb+srv://<user>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
MONGO_URI_DEFAUT = "mongodb://localhost:27017"
DB_NAME_DEFAUT = "voix_africaine"
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


def charger_uri_mongo(cli_uri: str | None) -> tuple[str, str]:
    """Résout l'URI MongoDB + nom de base (compatible Atlas + local)."""
    if cli_uri:
        uri = cli_uri
    else:
        uri = os.environ.get("MONGO")
        if not uri:
            # Lit le .env du projet (à côté de scripts/) sans dépendance externe
            env_path = Path(__file__).resolve().parent.parent / ".env"
            if env_path.exists():
                for ligne in env_path.read_text(encoding="utf-8").splitlines():
                    ligne = ligne.strip()
                    if ligne.startswith("MONGO=") and not ligne.startswith("MONGO_DB_NAME"):
                        uri = ligne.split("=", 1)[1].strip().strip("'\"")
                        break
        if not uri:
            uri = MONGO_URI_DEFAUT
    db_name = os.environ.get("MONGO_DB_NAME", DB_NAME_DEFAUT)
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if "MONGO_DB_NAME" not in os.environ and env_path.exists():
        for ligne in env_path.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if ligne.startswith("MONGO_DB_NAME="):
                db_name = ligne.split("=", 1)[1].strip().strip("'\"")
                break
    # pymongo gère nativement mongodb+srv:// (Atlas) si dnspython est installé
    # (déjà dans requirements.txt). serverSelectionTimeoutMS évite d'attendre
    # indéfiniment si l'IP n'est pas autorisée dans Network Access.
    return uri, db_name


def trouver_txt() -> Path | None:
    for candidat in TXT_CANDIDATS:
        if candidat.exists() and candidat.stat().st_size > 0:
            return candidat
    return None


def extraire_pdf_vers_txt(pdf: Path, sortie: Path) -> bool:
    """Extrait le PDF avec pdftotext (poppler) si le .txt est absent."""
    if sortie.exists() and sortie.stat().st_size > 0:
        return True
    if not pdf.exists():
        return False
    try:
        r = subprocess.run(
            ["pdftotext", "-layout", str(pdf), str(sortie)],
            capture_output=True, text=True, timeout=120,
        )
        return r.returncode == 0 and sortie.exists()
    except Exception as e:
        print(f"⚠️ pdftotext indisponible : {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Importe « La chèvre de ma mère » dans MongoDB (local ou Atlas)."
    )
    parser.add_argument("--mongo-uri", default=None, help="URI MongoDB (ex. mongodb+srv://... Atlas)")
    parser.add_argument("--db", default=None, help="Nom de la base (défaut: MONGO_DB_NAME du .env)")
    parser.add_argument("--txt", default=None, help="Chemin du texte extrait du PDF")
    parser.add_argument("--pdf", default=str(PDF_DEFAUT), help="Chemin du PDF source")
    args = parser.parse_args()

    mongo_uri, db_name = charger_uri_mongo(args.mongo_uri)
    if args.db:
        db_name = args.db
    masquee = re.sub(r"://([^:]+):([^@]+)@", r"://\\1:****@", mongo_uri)
    print(f"🔌 MongoDB : {masquee}  | base : {db_name}")

    # --- Texte source ---
    txt_path = Path(args.txt) if args.txt else trouver_txt()
    if txt_path is None or not txt_path.exists():
        print("📄 .txt introuvable, extraction depuis le PDF…")
        sortie = Path("/tmp/chevre.txt")
        if not extraire_pdf_vers_txt(Path(args.pdf), sortie):
            print(f"❌ Fichier introuvable : {sortie} (ni " + ", ".join(map(str, TXT_CANDIDATS)) + ")")
            print(f"   Extrayez d'abord le PDF : pdftotext -layout \"{args.pdf}\" /tmp/chevre.txt")
            return 1
        txt_path = sortie
    print(f"📄 Texte source : {txt_path}")
    try:
        lignes = txt_path.read_text(encoding="utf-8").split("\n")
    except UnicodeDecodeError:
        lignes = txt_path.read_text(encoding="latin-1").split("\n")
    if len(lignes) < 6012:
        print(f"⚠️ Texte plus court qu'attendu ({len(lignes)} lignes) — on ajuste le découpage.")
        # Ajustement proportionnel du dernier chapitre pour ne pas perdre de texte
        ratio = len(lignes) / 6012
        ajuste = []
        for debut, fin, numero, titre in DECOUPAGE:
            ajuste.append((int(debut * ratio) or 1, int(fin * ratio), numero, titre))
        decoupage = ajuste
    else:
        decoupage = DECOUPAGE

    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=15000)
        client.admin.command("ping")
    except Exception as e:
        print(f"❌ Connexion MongoDB impossible : {e}")
        print("   Atlas ? Vérifiez : 1) user/password dans l'URI  2) Network Access → autoriser votre IP (ou 0.0.0.0/0 en dev)  3) nom du cluster.")
        return 1
    db = client[db_name]
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
    for debut, fin, numero, titre in decoupage:
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
