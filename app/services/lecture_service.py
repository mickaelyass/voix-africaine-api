from fastapi import HTTPException, status, Depends

from app.auth_utils import get_current_user
from app.database import db
from app.models import Lecture, Chapitre



async def create_lecture(lecture: Lecture, current_user: dict = Depends(get_current_user)):
    # Vérifier que le chapitre existe et est public ou appartient à l'utilisateur
    chapitre = await db["chapitres"].find_one({"id": lecture.chapitre_id})
    if not chapitre:
        raise HTTPException(status_code=404, detail="Chapitre non trouvé")

    if not chapitre.get("is_public") and str(chapitre.get("created_by")) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Accès refusé")

    # Enregistrer la lecture
    lecture.user_id = current_user["id"]
    await db["lectures"].update_one(
        {"user_id": lecture.user_id, "chapitre_id": lecture.chapitre_id},
        {"$set": lecture.model_dump()},
        upsert=True
    )
    return await db["lectures"].find_one({
        "user_id": lecture.user_id,
        "chapitre_id": lecture.chapitre_id
    })


async def get_user_lectures(user_id: str, current_user: dict):
    if user_id != current_user["id"] and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    return await db["lectures"].find({"user_id": user_id}).to_list(100)