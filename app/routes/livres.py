from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth_utils import get_current_user, require_admin
from app.models import Livre
from app.services.livre_service import (
    create_livre,
    get_livre,
    update_livre,
    delete_livre,
    get_public_livres
)


router = APIRouter(prefix="/livres", tags=["Livres"])

@router.post("/", response_model=Livre)
async def create_new_livre(
    livre: Livre,
    current_user: dict = Depends(require_admin)
):
    return await create_livre(livre, current_user)

@router.get("/public/", response_model=list[Livre])
async def list_public_livres(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    return await get_public_livres(skip=skip, limit=limit)

@router.get("/{livre_id}", response_model=Livre)
async def read_livre(livre_id: str, current_user: dict = Depends(get_current_user)):
    return await get_livre(livre_id, current_user)

@router.put("/{livre_id}", response_model=Livre)
async def update_existing_livre(
    livre_id: str,
    livre: Livre,
    current_user: dict = Depends(require_admin)
):
    return await update_livre(livre_id, livre, current_user)
    

@router.delete("/{livre_id}")
async def remove_livre(
    livre_id: str,
    current_user: dict = Depends(require_admin)
):
    return await delete_livre(livre_id, current_user)