"""Logique métier du CRUD des commentaires horodatés.

Conventions d'identification (alignées sur le reste de l'API) :

- un commentaire est rattaché à un chapitre via le champ **string** ``id``
  fourni par le client, comme ``/chapitres`` ;
- ``user_id`` est stocké sous forme de **chaîne** (format ObjectId), ce qui est
  cohérent avec les documents déjà en base ;
- l'auteur d'un commentaire est **toujours déduit du token JWT** côté route :
  ``CommentInput.user_id`` n'est conservé que pour ne pas casser les clients
  existants et n'est jamais utilisé.
"""

from datetime import datetime
from typing import Dict, List, Optional

from bson import ObjectId
from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from app.database import db
from app.models import ChapitreWithComments, CommentairePublic, UserPublic


class CommentInput(BaseModel):
    """Corps accepté par ``POST /commentaires/``.

    ``user_id`` est déprécié : il est ignoré, l'auteur du commentaire étant
    déduit du token d'authentification.
    """

    contenu: str = Field(..., min_length=1, max_length=1000)
    timestamp: float = Field(
        0.0, ge=0, description="Position temporelle dans l'audio (en secondes)"
    )
    chapitre_id: str = Field(..., min_length=1, description="ID string du chapitre")
    user_id: Optional[str] = Field(
        None,
        deprecated=True,
        description="Ignoré : l'auteur du commentaire est déduit du token.",
    )


def _to_object_id(value: Optional[str]) -> Optional[ObjectId]:
    """Convertit une chaîne en ``ObjectId``, ou ``None`` si elle est invalide."""
    if not value or not ObjectId.is_valid(value):
        return None
    return ObjectId(value)


def _user_public_from_doc(user: dict) -> UserPublic:
    """Construit un ``UserPublic`` tolérant aux documents anciens/incomplets."""
    return UserPublic(
        id=str(user["_id"]),
        email=user.get("email") or "",
        full_name=user.get("full_name") or "",
        role=user.get("role") or "user",
        created_at=user.get("created_at") or datetime.utcnow(),
    )


def _to_public_commentaire(
    doc: dict, user_info: Optional[UserPublic]
) -> CommentairePublic:
    """Convertit un document MongoDB en ``CommentairePublic``."""
    created_at = doc.get("created_at") or datetime.utcnow()

    return CommentairePublic(
        _id=str(doc["_id"]),
        contenu=doc.get("contenu") or "",
        timestamp=doc.get("timestamp") or 0.0,
        chapitre_id=doc.get("chapitre_id"),
        user_info=user_info,
        created_at=created_at,
        updated_at=doc.get("updated_at") or created_at,
    )


async def _user_public_for(user_id: Optional[str]) -> Optional[UserPublic]:
    """Récupère les infos publiques d'un utilisateur, ou ``None`` s'il n'existe pas."""
    object_id = _to_object_id(user_id)
    if not object_id:
        return None

    user = await db["users"].find_one({"_id": object_id})
    return _user_public_from_doc(user) if user else None


class CommentaireService:

    @staticmethod
    async def create_commentaire(
        comment_input: CommentInput,
        user_id: str,
    ) -> CommentairePublic:
        """Crée un commentaire au nom de l'utilisateur authentifié."""
        if not ObjectId.is_valid(user_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ID utilisateur invalide",
            )

        if not await db["chapitres"].find_one({"id": comment_input.chapitre_id}):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chapitre non trouvé",
            )

        now = datetime.utcnow()
        comment_data = {
            "contenu": comment_input.contenu,
            "timestamp": comment_input.timestamp,
            "chapitre_id": comment_input.chapitre_id,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
            "is_public": True,
        }

        result = await db["commentaires"].insert_one(comment_data)

        new_comment = await db["commentaires"].find_one({"_id": result.inserted_id})
        if not new_comment:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Échec de la création du commentaire",
            )

        return _to_public_commentaire(new_comment, await _user_public_for(user_id))

    @staticmethod
    async def get_commentaires_for_chapitre(
        chapitre_id: str,
        current_user_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[CommentairePublic]:
        """Commentaires d'un chapitre, du plus récent au plus ancien.

        ``skip`` et ``limit`` sont réellement appliqués (la méthode forçait
        auparavant ``.limit(10)`` en ignorant ces paramètres).
        """
        safe_skip = max(skip, 0)
        safe_limit = limit if limit and limit > 0 else 100

        docs = await (
            db["commentaires"]
            .find({"chapitre_id": chapitre_id})
            .sort("created_at", -1)
            .skip(safe_skip)
            .limit(safe_limit)
            .to_list(length=safe_limit)
        )

        commentaires: List[CommentairePublic] = []
        users_cache: Dict[str, Optional[UserPublic]] = {}

        for doc in docs:
            key = str(doc.get("user_id") or "")
            if key not in users_cache:
                users_cache[key] = await _user_public_for(key)
            commentaires.append(_to_public_commentaire(doc, users_cache[key]))

        return commentaires

    @staticmethod
    async def get_chapitre_with_comments(
        chapitre_id: str,
        current_user_id: Optional[str] = None,
    ) -> ChapitreWithComments:
        """Récupère un chapitre (identifié par son ``id`` string) et ses commentaires."""
        chapitre = await db["chapitres"].find_one({"id": chapitre_id})
        if not chapitre:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chapitre non trouvé",
            )

        commentaires = await CommentaireService.get_commentaires_for_chapitre(
            chapitre_id=chapitre_id,
            current_user_id=current_user_id,
        )

        chapitre_data = {
            **chapitre,
            "id": chapitre.get("id") or str(chapitre["_id"]),
            "commentaires": commentaires,
        }

        return ChapitreWithComments(**chapitre_data)

    @staticmethod
    async def get_all_commentaires(
        skip: int = 0,
        limit: int = 1000,
    ) -> List[CommentairePublic]:
        """Tous les commentaires publics, enrichis de leur auteur.

        ``commentaires.user_id`` est stocké en chaîne alors que ``users._id`` est
        un ``ObjectId`` : la jointure convertit explicitement le type via
        ``$convert``, sans quoi ``$lookup`` ne renvoyait aucun utilisateur (et la
        liste finissait vide).
        """
        safe_skip = max(skip, 0)
        safe_limit = limit if limit and limit > 0 else 1000

        pipeline = [
            {"$match": {"is_public": {"$ne": False}}},
            {"$sort": {"created_at": -1}},
            {"$skip": safe_skip},
            {"$limit": safe_limit},
            {
                "$lookup": {
                    "from": "users",
                    "let": {"uid": "$user_id"},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {
                                    "$eq": [
                                        "$_id",
                                        {
                                            "$convert": {
                                                "input": "$$uid",
                                                "to": "objectId",
                                                "onError": None,
                                                "onNull": None,
                                            }
                                        },
                                    ]
                                }
                            }
                        },
                        {
                            "$project": {
                                "email": 1,
                                "full_name": 1,
                                "role": 1,
                                "created_at": 1,
                            }
                        },
                    ],
                    "as": "user_info",
                }
            },
            {"$addFields": {"user_info": {"$arrayElemAt": ["$user_info", 0]}}},
        ]

        comments = await db["commentaires"].aggregate(pipeline).to_list(
            length=safe_limit
        )

        resultat: List[CommentairePublic] = []
        for comment in comments:
            user = comment.pop("user_info", None)
            user_info = _user_public_from_doc(user) if user else None
            resultat.append(_to_public_commentaire(comment, user_info))

        return resultat

    @staticmethod
    async def delete_commentaire(comment_id: str, user_id: str) -> bool:
        """Supprime un commentaire si l'utilisateur en est l'auteur ou est admin."""
        object_id = _to_object_id(comment_id)
        if not object_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Commentaire non trouvé",
            )

        comment = await db["commentaires"].find_one({"_id": object_id})
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Commentaire non trouvé",
            )

        if str(comment.get("user_id")) != str(user_id):
            user = await _user_public_for(user_id)
            if not user or user.role != "admin":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Vous ne pouvez supprimer que vos propres commentaires",
                )

        result = await db["commentaires"].delete_one({"_id": object_id})
        return result.deleted_count > 0