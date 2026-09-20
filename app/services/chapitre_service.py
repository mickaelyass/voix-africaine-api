from fastapi import HTTPException, status,  UploadFile
from app.models import Chapitre, ChapitrePublic
import uuid
import io
import math
from pydub import AudioSegment
import cloudinary.uploader
from app.database import db  # adapte selon ton init_db
from datetime import datetime


async def create_chapitre(chapitre: Chapitre, current_user: dict):
    # Vérification du livre parent
    print("current_user =", current_user)
    livre = await db["livres"].find_one({"id": chapitre.livre_id})
    if not livre:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Livre spécifié n'existe pas"
        )

    # Vérification des doublons
    if await db["chapitres"].find_one({"id": chapitre.id}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un chapitre avec cet ID existe déjà"
        )

    if await db["chapitres"].find_one({
        "livre_id": chapitre.livre_id,
        "numero": chapitre.numero
    }):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Un chapitre avec le numéro {chapitre.numero} existe déjà pour ce livre"
        )

    chapitre_dict = chapitre.model_dump()
    try:
        created_by_id = str(current_user["_id"])
    except (KeyError, TypeError):
        raise HTTPException(status_code=500, detail="Utilisateur invalide : clé _id manquante")

    chapitre_dict["created_by"] = created_by_id

   

    result = await db["chapitres"].insert_one(chapitre_dict)
    return await db["chapitres"].find_one({"_id": result.inserted_id})


async def get_chapitre(chapitre_id: str, current_user: dict):
    chapitre = await db["chapitres"].find_one({"id": chapitre_id})
    if not chapitre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapitre non trouvé"
        )

    # Vérification des droits
    is_owner = str(chapitre.get("created_by")) == current_user["id"]
    if not chapitre.get("is_public") and not is_owner and current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé - Chapitre privé"
        )

    return chapitre


async def get_public_chapitre(chapitre_id: str):
    chapitre = await db["chapitres"].find_one({
        "id": chapitre_id,
        "is_public": True
    })
    if not chapitre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapitre public non trouvé"
        )
    return ChapitrePublic(**chapitre)


async def get_public_all_chapitre(skip: int = 0, limit: int = 100):
    safe_skip = max(skip, 0)
    safe_limit = min(max(limit, 1), 1000)
    chapitres = await db["chapitres"].find({
        "is_public": True
    }).skip(safe_skip).limit(safe_limit).to_list(safe_limit)
    return [ChapitrePublic(**ch) for ch in chapitres]
    
    
    
async def get_chapitres_du_livre(livre_id: str, current_user: dict, skip: int = 0, limit: int = 100):
    # Vérifier si le livre existe
    livre = await db["livres"].find_one({"id": livre_id})
    if not livre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Livre non trouvé"
        )

    # Admin peut tout voir
    if current_user["role"] == "admin":
        query = {"livre_id": livre_id}
    else:
        # Non-admin : voir les chapitres publics ou ceux qu'il a créés
        # NB : created_by est stocké sous forme de chaîne (str de l'ObjectId)
        query = {
            "livre_id": livre_id,
            "$or": [
                {"is_public": True},
                {"created_by": str(current_user["_id"])}
            ]
        }

    safe_skip = max(skip, 0)
    safe_limit = min(max(limit, 1), 1000)
    return await db["chapitres"].find(query).skip(safe_skip).limit(safe_limit).to_list(safe_limit)



async def toggle_chapitre_public(chapitre_id: str, current_user: dict):
    chapitre = await db["chapitres"].find_one({"id": chapitre_id})
    if not chapitre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapitre non trouvé"
        )

    # Seul l'auteur ou l'admin peut modifier la visibilité
    # NB : created_by est stocké en chaîne, _id est un ObjectId → comparer
    # les deux sous forme de chaîne (sinon l'auteur est toujours considéré
    # comme non propriétaire).
    is_owner = str(chapitre.get("created_by")) == str(current_user["_id"])
    if not is_owner and current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Action non autorisée"
        )

    new_status = not chapitre.get("is_public", False)
    await db["chapitres"].update_one(
        {"id": chapitre_id},
        {"$set": {"is_public": new_status}}
    )
    return {"is_public": new_status}
    

async def supprimer_chapitre(chapitre_id: str, current_user: dict ):
    # Vérifier l'existence du chapitre
    chapitre = await db["chapitres"].find_one({"id": chapitre_id})

    if not chapitre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapitre non trouvé"
        )

    # Vérifier les permissions
    is_admin = current_user["role"] == "admin"
    is_author = str(chapitre.get("created_by")) == str(current_user["_id"])

    if not (is_admin or is_author):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Non autorisé à supprimer ce chapitre"
        )

    # Suppression en cascade (cf. readme §6.2 point 15) : effacer d'abord le
    # fichier audio Cloudinary (sans le verrou « validé » : la suppression du
    # chapitre parent entraîne celle de son audio), puis les commentaires et
    # les lectures liés, avant le chapitre lui-même.
    public_id = chapitre.get("audio_public_id")
    resource_type = chapitre.get("audio_resource_type") or RESOURCE_TYPE_AUDIO
    if public_id:
        candidats = [public_id]
        chemin_duplique = f"chapitres/{chapitre_id}/{public_id}"
        if not public_id.startswith(f"chapitres/{chapitre_id}/chapitres/"):
            candidats.append(chemin_duplique)
        for candidat in candidats:
            try:
                reponse = cloudinary.uploader.destroy(
                    candidat,
                    resource_type=resource_type
                )
            except Exception as e:
                print(
                    "⚠️ Erreur suppression Cloudinary :",
                    e
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Impossible de supprimer l'audio sur Cloudinary"
                )
            if (reponse or {}).get("result") == "ok":
                break

    await db["commentaires"].delete_many({"chapitre_id": chapitre_id})
    await db["lectures"].delete_many({"chapitre_id": chapitre_id})

    # Suppression effective
    result = await db["chapitres"].delete_one({"id": chapitre_id})

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Échec de la suppression du chapitre"
        )

    return {"message": "Chapitre supprimé avec succès"}



# Taille maximale d'un fichier audio accepté : 25 Mo (cf. readme §5 point 11).
MAX_AUDIO_BYTES = 25 * 1024 * 1024

ALLOWED_MIMES = {"audio/webm", "audio/ogg", "audio/mpeg", "audio/wav", "audio/mp3", "audio/mp4", "audio/aac", "audio/x-wav", "audio/x-m4a", "audio/m4a", "audio/opus", "audio/flac"}

# Certains navigateurs (Safari, MediaRecorder sans MIME supporte) envoient le
# blob sans type exploitable ("application/octet-stream"). On accepte alors le
# fichier sur la base de son extension, elle-meme deduite du MIME reel de
# l'enregistrement cote frontend (cf. AudioRecorderUploader.jsx).
ALLOWED_EXTENSIONS = {"webm", "ogg", "oga", "opus", "mp3", "mpga", "mpeg", "mp4", "m4a", "wav", "aac", "flac"}

# Cloudinary classe les fichiers audio dans la ressource « video ».
RESOURCE_TYPE_AUDIO = "video"

def normalize_mime(content_type: str) -> str:
    """Retire les parametres (ex: 'audio/webm;codecs=opus' -> 'audio/webm')."""
    return (content_type or "").split(";")[0].strip().lower()

def get_extension_from_filename(filename: str):
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()

async def update_chapitre_audio(
    chapitre_id: str,
    file: UploadFile,
    current_user: dict
):
    # ==========================================
    # 1. Vérifier que le chapitre existe
    # ==========================================

    print("TYPE REÇU:", file.content_type)

    chapitre = await db["chapitres"].find_one({
        "id": chapitre_id
    })

    if not chapitre:
        raise HTTPException(
            status_code=404,
            detail="Chapitre non trouvé"
        )


    # ==========================================
    # 2. Permissions
    # ==========================================

    # Tout utilisateur authentifie peut enregistrer / uploader l'audio
    # d'un chapitre. (La suppression reste reservee a l'admin,
    # cf. supprimer_audio_chapitre.)

    # ==========================================
    # 3. Audio déjà validé = verrouillé
    # ==========================================

    if chapitre.get("audio_validated", False):

        raise HTTPException(
            status_code=403,
            detail=(
                "Cet audio a déjà été validé par un "
                "administrateur et ne peut plus être modifié."
            )
        )


    # ==========================================
    # 5. Vérification du type MIME
    # ==========================================

    extension = get_extension_from_filename(file.filename)

    if (
        normalize_mime(file.content_type) not in ALLOWED_MIMES
        and extension not in ALLOWED_EXTENSIONS
    ):
        raise HTTPException(
            status_code=400,
            detail="Type de fichier audio non supporté"
        )


    # ==========================================
    # 6. Lire le fichier
    # ==========================================

    file.file.seek(0)

    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="Le fichier audio est vide"
        )

    if len(file_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                "Fichier audio trop volumineux "
                f"({len(file_bytes)} octets, maximum {MAX_AUDIO_BYTES})."
            ),
        )


    file_io = io.BytesIO(file_bytes)
    file_io.seek(0)


    # ==========================================
    # 7. Upload Cloudinary
    # ==========================================

    # Le dossier est deja porte par le public_id. Passer EN PLUS `folder` fait
    # doubler le chemin cote Cloudinary (chapitres/{id}/chapitres/{id}/{uuid})
    # et rend le fichier introuvable avec l'`audio_public_id` reellement stocke.
    dossier = f"chapitres/{chapitre_id}"

    public_id_demande = f"{dossier}/{uuid.uuid4()}"

    try:

        upload_result = cloudinary.uploader.upload(
            file_io,
            # Un fichier audio = ressource « video » chez Cloudinary.
            resource_type=RESOURCE_TYPE_AUDIO,
            public_id=public_id_demande,
            overwrite=False,
        )

    except Exception as e:

        print(
            "💥 Cloudinary upload error :",
            e
        )

        raise HTTPException(
            status_code=500,
            detail=f"Erreur upload Cloudinary: {e}"
        )


    # Identifiants reels renvoyes par Cloudinary : indispensables pour pouvoir
    # supprimer le fichier plus tard (cf. supprimer_audio_chapitre).
    public_id = upload_result.get("public_id") or public_id_demande
    resource_type = upload_result.get("resource_type") or RESOURCE_TYPE_AUDIO


    # ==========================================
    # 8. Récupérer URL sécurisée
    # ==========================================

    audio_url = (
        upload_result.get("secure_url")
        or upload_result.get("url")
    )

    if not audio_url:

        raise HTTPException(
            status_code=500,
            detail=(
                "Impossible d'obtenir l'URL "
                "du fichier uploadé"
            )
        )


    # ==========================================
    # 9. Calculer la durée
    # ==========================================

    duration = None

    try:

        ext = get_extension_from_filename(
            file.filename
        )

        audio = AudioSegment.from_file(
            io.BytesIO(file_bytes),
            format=ext if ext else None
        )

        duration = math.ceil(
            audio.duration_seconds
        )

    except Exception as e:

        print(
            "⚠️ Impossible de déterminer "
            "la durée audio :",
            e
        )

        duration = None


    # ==========================================
    # 10. Préparer la mise à jour
    # ==========================================

    updated_data = {
        "audio_url": audio_url,
        "duration_sec": duration,
         "audio_public_id": public_id,
        "audio_resource_type": resource_type,
        # Un nouvel audio n'est pas validé
        "audio_validated": False,

        # On efface l'ancienne validation
        "audio_validated_at": None,
        "audio_validated_by": None,
    }


    # ==========================================
    # 11. NE PAS modifier created_by
    # ==========================================

    # created_by reste l'auteur original
    #
    # On ne fait PAS :
    #
    # "created_by": current_user["id"]


    # ==========================================
    # 12. Mise à jour MongoDB
    # ==========================================

    result = await db["chapitres"].update_one(
        {"id": chapitre_id},
        {"$set": updated_data}
    )

    if result.modified_count == 0:

        raise HTTPException(
            status_code=500,
            detail="Échec de la mise à jour de l'audio"
        )


    # ==========================================
    # 13. Retourner le chapitre mis à jour
    # ==========================================

    updated_chapitre = await db["chapitres"].find_one({
        "id": chapitre_id
    })

    if updated_chapitre and "_id" in updated_chapitre:

        updated_chapitre["_id"] = str(
            updated_chapitre["_id"]
        )

    return updated_chapitre


async def valider_audio_chapitre( chapitre_id: str,current_user: dict):
    chapitre = await db["chapitres"].find_one({
        "id": chapitre_id
    })

    if not chapitre:
        raise HTTPException(
            status_code=404,
            detail="Chapitre non trouvé"
        )

    if not chapitre.get("audio_url"):
        raise HTTPException(
            status_code=400,
            detail="Impossible de valider un chapitre sans audio"
        )

    if chapitre.get("audio_validated", False):
        raise HTTPException(
            status_code=400,
            detail="Cet audio est déjà validé"
        )

    now = datetime.utcnow()

    await db["chapitres"].update_one(
        {"id": chapitre_id},
        {
            "$set": {
                "audio_validated": True,
                "audio_validated_at": now,
                "audio_validated_by": current_user["id"]
            }
        }
    )

    return await db["chapitres"].find_one({
        "id": chapitre_id
    })   

async def supprimer_audio_chapitre(
    chapitre_id: str,
    current_user: dict
):
    # ==========================================
    # 1. Vérifier que le chapitre existe
    # ==========================================

    chapitre = await db["chapitres"].find_one({
        "id": chapitre_id
    })

    if not chapitre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapitre non trouvé"
        )

    # ==========================================
    # 2. Vérifier qu'un audio existe
    # ==========================================

    if not chapitre.get("audio_url"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aucun audio n'est associé à ce chapitre"
        )

    # ==========================================
    # 3. Audio validé = verrouillé
    # ==========================================

    if chapitre.get("audio_validated", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Cet audio a été validé par un administrateur "
                "et ne peut plus être supprimé."
            )
        )

    # ==========================================
    # 4. Vérifier les droits : admin uniquement
    # ==========================================

    if current_user.get("role", "user") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "La suppression d'un audio est réservée "
                "aux administrateurs."
            )
        )

    # ==========================================
    # 6. Récupérer le public_id Cloudinary
    # ==========================================

    public_id = chapitre.get("audio_public_id")

    resource_type = (
        chapitre.get("audio_resource_type")
        or RESOURCE_TYPE_AUDIO
    )

    # ==========================================
    # 7. Supprimer le fichier Cloudinary
    # ==========================================

    if public_id:

        # Les audios enregistres avant la correction du chemin Cloudinary ont
        # ete stockes sous `chapitres/{id}/chapitres/{id}/{uuid}` alors que
        # `audio_public_id` ne contient que `chapitres/{id}/{uuid}`. On retente
        # donc avec le chemin duplique pour ne pas laisser de fichiers
        # orphelins (cas de tous les audios deja en base).
        candidats = [public_id]

        chemin_duplique = f"chapitres/{chapitre_id}/{public_id}"

        if not public_id.startswith(f"chapitres/{chapitre_id}/chapitres/"):
            candidats.append(chemin_duplique)

        for candidat in candidats:

            try:
                reponse = cloudinary.uploader.destroy(
                    candidat,
                    resource_type=resource_type
                )

            except Exception as e:

                print(
                    "⚠️ Erreur suppression Cloudinary :",
                    e
                )

                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "Impossible de supprimer "
                        "l'audio sur Cloudinary"
                    )
                )

            if (reponse or {}).get("result") == "ok":
                break

            print(
                "⚠️ Fichier Cloudinary introuvable :",
                candidat,
                reponse
            )

    # ==========================================
    # 8. Supprimer les données audio de MongoDB
    # ==========================================

    result = await db["chapitres"].update_one(
        {"id": chapitre_id},
        {
            "$set": {
                "audio_url": None,
                "audio_public_id": None,
                "audio_resource_type": None,
                "duration_sec": None,

                "audio_validated": False,
                "audio_validated_at": None,
                "audio_validated_by": None
            }
        }
    )

    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Échec de la suppression de l'audio"
        )

    # ==========================================
    # 9. Retourner le chapitre mis à jour
    # ==========================================

    updated_chapitre = await db["chapitres"].find_one({
        "id": chapitre_id
    })

    if updated_chapitre and "_id" in updated_chapitre:
        updated_chapitre["_id"] = str(
            updated_chapitre["_id"]
        )

    return updated_chapitre