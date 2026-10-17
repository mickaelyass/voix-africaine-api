import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth_utils import get_current_active_user, require_admin
from app.middleware import get_client_ip, rate_limiter
from app.models import Token, UserPublic, UserCreate
from app.services.auth_service import (
    register_user,
    authenticate_for_token,
    get_current_user_profile, get_all_user, _get_user_public_info,

)

logger = logging.getLogger("voix_africaine.auth")

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=UserPublic)
async def register(user_data: UserCreate):
    return await register_user(user_data)

@router.post("/token", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request = None,
):
    # ==========================================
    # RATE LIMITING — protection brute-force
    # ==========================================
    ip = get_client_ip(request) if request else "unknown"

    if not rate_limiter.check_auth(ip):
        logger.warning(
            "auth_rate_limited",
            extra={"ip": ip, "username": form_data.username},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de tentatives de connexion. Réessayez dans une minute.",
        )

    rate_limiter.record_auth(ip)

    # ==========================================
    # AUTHENTIFICATION AVEC TIMING
    # ==========================================
    start = time.perf_counter()
    try:
        result = await authenticate_for_token(form_data.username, form_data.password)
    except HTTPException:
        duration = time.perf_counter() - start
        logger.warning(
            "auth_failed",
            extra={
                "ip": ip,
                "username": form_data.username,
                "duration_ms": round(duration * 1000, 1),
            },
        )
        raise

    duration = time.perf_counter() - start
    logger.info(
        "auth_success",
        extra={
            "ip": ip,
            "username": form_data.username,
            "duration_ms": round(duration * 1000, 1),
        },
    )

    # Reset du compteur après un login réussi
    rate_limiter.reset(ip)

    return result

@router.get("/me", response_model=UserPublic)
async def read_users_me(current_user: dict = Depends(get_current_active_user)):
    return {
        "id": str(current_user["_id"]),
        "email": current_user["email"],
        "full_name": current_user["full_name"],
        "role": current_user.get("role", "user"),
        "created_at": current_user["created_at"]
    }

@router.post("/google-auth")

async def google_auth_route(token: str):
    # Implémentation Google OAuth
     pass

@router.get("/",response_model=list[UserPublic])
async def alluser(current_user: dict = Depends(require_admin)):
    return await get_all_user()


@router.get("/{user_id}", response_model=UserPublic)
async def get_user(
    user_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    # Données personnelles : seul l'utilisateur lui-même ou un
    # administrateur peut consulter un profil (cf. readme §5 point 7).
    if (
        current_user.get("role", "user") != "admin"
        and str(current_user["_id"]) != user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé",
        )
    return await _get_user_public_info(user_id)