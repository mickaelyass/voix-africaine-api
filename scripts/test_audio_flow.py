"""Test de non-regression du flux audio : enregistrement -> Cloudinary -> suppression.

Il verifie les regles metier de l'enregistrement vocal :

1. un **utilisateur standard** (`role: user`) peut creer un chapitre puis
   enregistrer/envoyer son audio (champ multipart `file`) ;
2. l'audio est **relisible apres l'envoi** (URL Cloudinary non dupliquee,
   fichier reellement present sur Cloudinary, `duration_sec` calculee) ;
3. la **suppression de l'audio et la validation** sont **reservees a l'admin**
   (403 pour un utilisateur standard) ;
4. la suppression admin **efface reellement le fichier** Cloudinary, y compris
   les audios historiques stockes sous l'ancien chemin duplique
   `chapitres/{id}/chapitres/{id}/{uuid}` ;
5. un navigateur qui n'annonce pas de MIME audio est accepte via l'extension
   du fichier, un fichier non audio est refuse.

L'API et `mongod` doivent deja tourner (cf. scripts/run_dev.sh). Le script se
nettoie lui-meme : chapitres, livre, utilisateur de test et fichiers Cloudinary
crees pendant le test sont supprimes a la fin.

Usage, depuis la racine du projet :

    env/bin/python -m scripts.test_audio_flow
    API_URL=http://127.0.0.1:9000 env/bin/python -m scripts.test_audio_flow

Code de sortie 0 si tout passe, 1 sinon.

Attention : ce test effectue de vrais appels Cloudinary (envoi puis suppression
d'un fichier audio d'une seconde). Il consomme donc un peu du quota du compte.
"""

import io
import math
import os
import struct
import sys
import uuid
import wave

import httpx

from app.config import settings

BASE = os.environ.get("API_URL", "http://127.0.0.1:8000")
ADMIN_EMAIL = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@voixafricaine.com")
ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "Admin@Voix2026")
RESOURCE_TYPE_AUDIO = "video"

results: list[tuple[str, bool, str]] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    """Enregistre une verification et affiche son resultat."""

    results.append((label, ok, detail))

    suffix = f" — {detail}" if detail else ""
    print(f"{'✅' if ok else '❌'} {label}{suffix}")

    return ok


def report() -> int:
    failed = [r for r in results if not r[1]]

    print()
    print("=" * 62)
    if failed:
        print(f"❌ {len(failed)}/{len(results)} vérifications en échec")
        for label, _, detail in failed:
            print(f"   - {label} {detail}")
        return 1

    print(f"✅ {len(results)}/{len(results)} vérifications réussies")
    return 0


def wav_bytes(duree_sec: float = 1.0, frequence: int = 440) -> bytes:
    """Genere un WAV mono minimal (utilise comme enregistrement de test)."""

    taux = 44100
    buffer = io.BytesIO()

    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taux)
        w.writeframes(
            b"".join(
                struct.pack("<h", int(12000 * math.sin(2 * math.pi * frequence * i / taux)))
                for i in range(int(taux * duree_sec))
            )
        )

    return buffer.getvalue()


def configurer_cloudinary():
    """Configure le SDK Cloudinary avec les identifiants du projet."""

    import cloudinary

    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )

    return cloudinary


def main() -> int:

    cloudinary = configurer_cloudinary()

    import cloudinary.api
    import cloudinary.uploader

    def existe_sur_cloudinary(public_id: str) -> bool:
        """Le fichier est-il reellement present sur Cloudinary ?"""

        try:
            cloudinary.api.resource(public_id, resource_type=RESOURCE_TYPE_AUDIO)
            return True
        except Exception:
            return False

    audio = wav_bytes()

    livre_id = str(uuid.uuid4())
    chapitre_id = str(uuid.uuid4())
    chapitre_herite_id = str(uuid.uuid4())
    chapitre_mime_id = str(uuid.uuid4())
    email = f"__test_audio_{uuid.uuid4().hex[:8]}@example.com"
    mot_de_passe = "TestAudio2026!"
    public_id_herite_reel = None
    chapitres = None
    users = None

    try:
        import pymongo

        client_mongo = pymongo.MongoClient(settings.MONGO)
        users = client_mongo[settings.MONGO_DB_NAME]["users"]
        chapitres = client_mongo[settings.MONGO_DB_NAME]["chapitres"]
    except Exception as e:
        print(f"⚠️  MongoDB injoignable via pymongo ({e}) : test du chemin hérité ignoré")

    admin = None

    try:
        with httpx.Client(base_url=BASE, timeout=90) as client:

            # ==========================================
            # 1. Authentification (admin + utilisateur standard)
            # ==========================================

            r = client.post("/auth/token", data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
            if not check("POST /auth/token (admin par défaut)", r.status_code == 200, f"HTTP {r.status_code}"):
                return report()

            admin = {"Authorization": f"Bearer {r.json()['access_token']}"}

            r = client.post("/auth/register", json={"email": email, "full_name": "Test Audio", "password": mot_de_passe})
            check("POST /auth/register (utilisateur standard)", r.status_code == 200, f"HTTP {r.status_code}")

            r = client.post("/auth/token", data={"username": email, "password": mot_de_passe})
            if not check("POST /auth/token (utilisateur standard)", r.status_code == 200, f"HTTP {r.status_code}"):
                return report()

            user = {"Authorization": f"Bearer {r.json()['access_token']}"}

            r = client.get("/auth/me", headers=user)
            check(
                "  → rôle 'user' (et non admin)",
                r.status_code == 200 and r.json().get("role") == "user",
                str(r.json().get("role") if r.status_code == 200 else r.status_code),
            )

            # ==========================================
            # 2. Un utilisateur standard crée les données de test
            # ==========================================

            r = client.post(
                "/livres/",
                headers=admin,
                json={
                    "id": livre_id,
                    "titre": f"__test_audio_livre_{livre_id[:8]}",
                    "auteur": "Test Audio",
                    "description": "Créé puis supprimé par scripts/test_audio_flow.py",
                    "is_public": True,
                },
            )
            check("POST /livres/ (admin)", r.status_code == 200, f"HTTP {r.status_code}")

            for cid, titre, numero in (
                (chapitre_id, "__test_audio", 1),
                (chapitre_herite_id, "__test_audio_herite", 2),
                (chapitre_mime_id, "__test_audio_mime", 3),
            ):
                r = client.post(
                    "/chapitres/",
                    headers=user,
                    json={
                        "id": cid,
                        "livre_id": livre_id,
                        "titre": titre,
                        "numero": numero,
                        "contenu_texte": "Texte de test.",
                        "is_public": True,
                    },
                )
                check(
                    f"POST /chapitres/ par un utilisateur standard ({titre})",
                    r.status_code == 200,
                    f"HTTP {r.status_code}",
                )

            # ==========================================
            # 3. Enregistrement/envoi par un utilisateur standard
            # ==========================================

            # Le champ multipart doit s'appeler "file" : c'est le nom du
            # paramètre déclaré côté FastAPI (`file: UploadFile = File(...)`).
            # Un autre nom de champ provoque un 422 et l'audio n'atteint jamais
            # Cloudinary (bug historique du frontend, champ "audio").
            r = client.put(
                f"/chapitres/{chapitre_id}/upload-audio",
                headers=user,
                files={"file": (f"chapitre-{chapitre_id}.wav", audio, "audio/wav")},
            )

            envoi_ok = check(
                "PUT /chapitres/{id}/upload-audio par un utilisateur standard (champ 'file')",
                r.status_code == 200,
                f"HTTP {r.status_code} {r.text[:160]}",
            )

            audio_envoye = r.json() if envoi_ok else {}
            public_id = audio_envoye.get("audio_public_id") or ""
            audio_url = audio_envoye.get("audio_url") or ""

            if envoi_ok:
                check("  → audio_url renseignée", audio_url.startswith("https://"), audio_url[:80])
                check(
                    "  → pas de dossier dupliqué dans l'URL Cloudinary",
                    f"/chapitres/{chapitre_id}/chapitres/" not in audio_url,
                    audio_url[:100],
                )
                check(
                    "  → audio_public_id = chemin réel du fichier",
                    public_id == f"chapitres/{chapitre_id}/{public_id.split('/')[-1]}",
                    public_id,
                )
                check("  → fichier réellement présent sur Cloudinary", existe_sur_cloudinary(public_id), public_id)
                check(
                    "  → audio_resource_type stocké",
                    audio_envoye.get("audio_resource_type") == RESOURCE_TYPE_AUDIO,
                    str(audio_envoye.get("audio_resource_type")),
                )
                check(
                    "  → duration_sec calculée (pydub + ffmpeg)",
                    (audio_envoye.get("duration_sec") or 0) >= 1,
                    str(audio_envoye.get("duration_sec")),
                )

            # ==========================================
            # 4. Relecture de l'audio enregistré
            # ==========================================

            r = client.get(f"/chapitres/livre/{livre_id}", headers=user)
            liste = {ch["id"]: ch for ch in r.json()} if r.status_code == 200 else {}
            check(
                "GET /chapitres/livre/{id} : audio visible pour un utilisateur standard",
                bool(liste.get(chapitre_id, {}).get("audio_url")),
                str(liste.get(chapitre_id, {}).get("audio_url"))[:80],
            )

            r = client.get(f"/chapitres/{chapitre_id}", headers=user)
            check(
                "GET /chapitres/{id} : audio relisible après l'enregistrement",
                r.status_code == 200 and bool(r.json().get("audio_url")),
                f"HTTP {r.status_code}",
            )

            # ==========================================
            # 5. Suppression et validation réservées à l'admin
            # ==========================================

            r = client.delete(f"/chapitres/{chapitre_id}/audio", headers=user)
            check(
                "DELETE /chapitres/{id}/audio refusé à un utilisateur standard (403)",
                r.status_code == 403,
                f"HTTP {r.status_code}",
            )

            r = client.patch(f"/chapitres/{chapitre_id}/validate-audio", headers=user)
            check(
                "PATCH /chapitres/{id}/validate-audio refusé à un utilisateur standard (403)",
                r.status_code == 403,
                f"HTTP {r.status_code}",
            )

            # ==========================================
            # 6. Suppression par l'admin : le fichier doit disparaître
            # ==========================================

            r = client.delete(f"/chapitres/{chapitre_id}/audio", headers=admin)
            check("DELETE /chapitres/{id}/audio autorisé à l'admin", r.status_code == 200, f"HTTP {r.status_code}")

            if public_id:
                check("  → fichier supprimé de Cloudinary", not existe_sur_cloudinary(public_id), public_id)

            # ==========================================
            # 7. Audios historiques (ancien chemin dupliqué)
            # ==========================================
            # Avant correction, `folder` ET `public_id` portaient le dossier :
            # le fichier était stocké sous `chapitres/{id}/chapitres/{id}/{uuid}`
            # alors que `audio_public_id` valait `chapitres/{id}/{uuid}`, ce qui
            # rendait la suppression admin inopérante (fichiers orphelins).

            if chapitres is not None:
                ancien_public_id = f"chapitres/{chapitre_herite_id}/{uuid.uuid4()}"

                import cloudinary.uploader

                upload = cloudinary.uploader.upload(
                    io.BytesIO(audio),
                    resource_type="auto",
                    public_id=ancien_public_id,
                    overwrite=False,
                    folder=f"chapitres/{chapitre_herite_id}",
                )
                public_id_herite_reel = upload["public_id"]

                check(
                    "Audio historique simulé au chemin dupliqué",
                    public_id_herite_reel.startswith(f"chapitres/{chapitre_herite_id}/chapitres/"),
                    public_id_herite_reel,
                )

                chapitres.update_one(
                    {"id": chapitre_herite_id},
                    {
                        "$set": {
                            "audio_url": upload["secure_url"],
                            "audio_public_id": ancien_public_id,
                            "duration_sec": 1,
                        }
                    },
                )

                r = client.delete(f"/chapitres/{chapitre_herite_id}/audio", headers=admin)
                check(
                    "DELETE /audio admin sur un audio au chemin hérité",
                    r.status_code == 200,
                    f"HTTP {r.status_code}",
                )
                check(
                    "  → fichier hérité supprimé de Cloudinary",
                    not existe_sur_cloudinary(public_id_herite_reel),
                    public_id_herite_reel,
                )

            # ==========================================
            # 8. Tolérance MIME (navigateurs sans type audio exploitable)
            # ==========================================

            r = client.put(
                f"/chapitres/{chapitre_mime_id}/upload-audio",
                headers=user,
                files={"file": (f"chapitre-{chapitre_mime_id}.wav", audio, "application/octet-stream")},
            )
            check(
                "Upload accepté malgré un MIME générique (repli sur l'extension)",
                r.status_code == 200,
                f"HTTP {r.status_code}",
            )

            r = client.put(
                f"/chapitres/{chapitre_mime_id}/upload-audio",
                headers=user,
                files={"file": ("fichier-interdit.exe", audio, "application/x-msdownload")},
            )
            check("Fichier non audio refusé (400)", r.status_code == 400, f"HTTP {r.status_code}")

            # ==========================================
            # 9. Propriété d'un chapitre (auteur non-admin)
            # ==========================================

            r = client.patch(f"/chapitres/{chapitre_mime_id}/toggle-public", headers=user)
            check(
                "PATCH /chapitres/{id}/toggle-public par son auteur non-admin",
                r.status_code == 200,
                f"HTTP {r.status_code}",
            )

    except Exception as e:
        check("Exécution du scénario complet", False, f"{type(e).__name__}: {e}")

    finally:
        # ==========================================
        # Nettoyage (idempotent, même en cas d'échec)
        # ==========================================

        if admin:
            try:
                with httpx.Client(base_url=BASE, timeout=30) as client:
                    for cid in (chapitre_id, chapitre_herite_id, chapitre_mime_id):
                        client.delete(f"/chapitres/{cid}/audio", headers=admin)
                        client.delete(f"/chapitres/{cid}", headers=admin)
                    client.delete(f"/livres/{livre_id}", headers=admin)
            except Exception as e:
                print(f"⚠️  Nettoyage HTTP incomplet : {e}")

        if public_id_herite_reel and existe_sur_cloudinary(public_id_herite_reel):
            try:
                cloudinary.uploader.destroy(public_id_herite_reel, resource_type=RESOURCE_TYPE_AUDIO)
            except Exception as e:
                print(f"⚠️  Nettoyage Cloudinary incomplet : {e}")

        if users is not None:
            try:
                users.delete_one({"email": email})
            except Exception as e:
                print(f"⚠️  Nettoyage utilisateur incomplet : {e}")

    return report()


if __name__ == "__main__":
    sys.exit(main())
