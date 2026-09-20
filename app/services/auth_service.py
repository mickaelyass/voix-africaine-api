from datetime import datetime, timedelta

from bson import ObjectId
from fastapi import HTTPException,status

from app.database import db
from app.models import UserCreate, UserInDB, UserPublic
from app.config import settings
from app.auth_utils import (
    get_password_hash,
    create_access_token,
    authenticate_user,
)

async def register_user(user_data: UserCreate):
    if await db["users"].find_one({"email": user_data.email}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    user_dict = {
        "email": user_data.email,
        "full_name": user_data.full_name,
        "hashed_password": get_password_hash(user_data.password),
        "disabled": False,
        "role": "user",  # Rôle par défaut
        "created_at": datetime.utcnow()
    }

    result = await db["users"].insert_one(user_dict)
    created_user = await db["users"].find_one({"_id": result.inserted_id})
    
    return {
        "id": str(created_user["_id"]),
        "email": created_user["email"],
        "full_name": created_user["full_name"],
        "created_at": created_user["created_at"],
        "role": created_user["role"]  # Important!
    }
    
async def authenticate_for_token(email: str, password: str):
    user = await authenticate_user(email, password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect credentials"
        )

    access_token = create_access_token(
        data={"sub": str(user["_id"])},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

def get_current_user_profile(user_data: dict):
    return {
        "id": str(user_data["_id"]),
        "email": user_data["email"],
        "full_name": user_data["full_name"],
        "created_at": user_data["created_at"]
    }

async def get_all_user() -> list[UserPublic]:
    users = await db["users"].find().to_list(1000)
    return [
        UserPublic(
            id=str(user["_id"]),
            email=user.get("email", ""),
            full_name=user.get("full_name", ""),
            role=user.get("role", "user"),
            created_at=user["created_at"],
        )
        for user in users
    ]

async def migrate_existing_users():
    await db["users"].update_many(
        {"role": {"$exists": False}},
        {"$set": {"role": "user"}}
    )


async def _get_user_public_info(user_id: str) -> UserPublic:
    """Récupère les infos publiques d'un utilisateur"""
    if not ObjectId.is_valid(user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID utilisateur invalide"
        )

    user = await db["users"].find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )

    return UserPublic(
        id=str(user["_id"]),
        email=user.get("email", ""),
        full_name=user.get("full_name", ""),
        role=user.get("role", "user"),
        created_at=user["created_at"]
    )
