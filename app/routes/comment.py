from typing import List

from fastapi import APIRouter, Depends, Query, status

from app.auth_utils import get_current_active_user, get_current_user
from app.models import ChapitreWithComments, CommentairePublic
from app.services.commentaire_service import CommentaireService, CommentInput

router = APIRouter(prefix="/commentaires", tags=["commentaires"])


@router.post("/", response_model=CommentairePublic)
async def create_comment(
    comment_input: CommentInput,
    current_user: dict = Depends(get_current_active_user),
):
    """Crée un commentaire au nom de l'utilisateur porteur du token.

    Un ``user_id`` éventuellement présent dans le corps est ignoré : l'auteur
    est toujours déduit du token (empêche l'usurpation d'identité).
    """
    return await CommentaireService.create_commentaire(
        comment_input,
        user_id=str(current_user["_id"]),
    )


@router.get("/", response_model=List[CommentairePublic])
async def get_commentaires_chapitre(
    chapitre_id: str = Query(..., min_length=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
):
    """Liste les commentaires d'un chapitre (pagination ``skip``/``limit``)."""
    return await CommentaireService.get_commentaires_for_chapitre(
        chapitre_id=chapitre_id,
        current_user_id=str(current_user["_id"]),
        skip=skip,
        limit=limit,
    )


@router.get("/user/{user_id}", response_model=List[CommentairePublic])
async def get_commentaires_user(
    user_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
):
    """Liste les commentaires d'un utilisateur (admin ou soi-même)."""
    if (
        current_user.get("role", "user") != "admin"
        and str(current_user["_id"]) != user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé",
        )
    return await CommentaireService.get_commentaires_for_user(
        user_id=user_id,
        skip=skip,
        limit=limit,
    )


@router.get("/all", response_model=List[CommentairePublic])
async def get_all_commentaires(
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=1000),
):
    """Liste tous les commentaires publics (liste vide si aucun commentaire)."""
    return await CommentaireService.get_all_commentaires(skip=skip, limit=limit)


@router.get("/chapitre/{chapitre_id}", response_model=ChapitreWithComments)
async def get_chapitre_complet(
    chapitre_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Récupère un chapitre (identifié par son ``id`` string) et ses commentaires."""
    return await CommentaireService.get_chapitre_with_comments(
        chapitre_id=chapitre_id,
        current_user_id=str(current_user["_id"]),
    )


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_commentaire(
    comment_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    """Supprime un commentaire (auteur ou administrateur)."""
    await CommentaireService.delete_commentaire(
        comment_id=comment_id,
        user_id=str(current_user["_id"]),
    )
    return None