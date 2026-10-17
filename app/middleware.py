
import time
import logging
from collections import defaultdict, deque
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logger = logging.getLogger("voix_africaine.http")


# ==========================================
# RATE LIMITER (en mémoire, par IP)
# ==========================================

class RateLimiter:
    """
    Limiteur de requêtes basé sur une fenêtre glissante, stocké en mémoire.

    Suffisant pour un déploiement single-instance (Render free/starter).
    Pour un déploiement multi-instances, migrer vers Redis (ex: `limits`).
    """

    def __init__(self):
        # dict[ip] = deque[timestamps]
        self._auth_attempts: dict[str, deque[float]] = defaultdict(deque)
        self._global_requests: dict[str, deque[float]] = defaultdict(deque)

    def _clean(self, dq: deque[float], window: int) -> None:
        now = time.monotonic()
        while dq and now - dq[0] > window:
            dq.popleft()

    def check_auth(self, ip: str) -> bool:
        """Retourne True si l'IP peut tenter une connexion."""
        if not settings.RATE_LIMIT_ENABLED:
            return True
        dq = self._auth_attempts[ip]
        self._clean(dq, settings.RATE_LIMIT_AUTH_WINDOW_SECONDS)
        return len(dq) < settings.RATE_LIMIT_AUTH_ATTEMPTS

    def record_auth(self, ip: str) -> None:
        self._auth_attempts[ip].append(time.monotonic())

    def check_global(self, ip: str) -> bool:
        """Retourne True si l'IP peut faire une requête globale."""
        if not settings.RATE_LIMIT_ENABLED:
            return True
        dq = self._global_requests[ip]
        self._clean(dq, settings.RATE_LIMIT_GLOBAL_WINDOW_SECONDS)
        return len(dq) < settings.RATE_LIMIT_GLOBAL_REQUESTS

    def record_global(self, ip: str) -> None:
        self._global_requests[ip].append(time.monotonic())

    def reset(self, ip: str) -> None:
        """Réinitialise les compteurs d'une IP (utile après un login réussi)."""
        self._auth_attempts.pop(ip, None)


rate_limiter = RateLimiter()


def get_client_ip(request: Request) -> str:
    """Extrait l'IP réelle du client derrière un proxy (Render, Netlify)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ==========================================
# MIDDLEWARE LOGGING + RATE LIMITING
# ==========================================

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Journalise chaque requête HTTP avec sa durée, son statut et l'IP.
    Format JSON structuré pour ingestion par un outil (Loki, ELK, etc.).
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        ip = get_client_ip(request)

        # Rate limit global
        if not rate_limiter.check_global(ip):
            duration = time.perf_counter() - start
            logger.warning(
                "rate_limited",
                extra={
                    "ip": ip,
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": 429,
                    "duration_ms": round(duration * 1000, 1),
                },
            )
            return Response(
                content='{"detail":"Trop de requêtes. Réessayez plus tard."}',
                status_code=429,
                media_type="application/json",
            )

        rate_limiter.record_global(ip)

        # Log de la requête
        response = await call_next(request)
        duration = time.perf_counter() - start

        logger.info(
            "http_request",
            extra={
                "ip": ip,
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 1),
                "user_agent": request.headers.get("user-agent", ""),
            },
        )

        # En-têtes de monitoring
        response.headers["X-Response-Time-Ms"] = str(round(duration * 1000, 1))

        return response


# ==========================================
# CONFIGURATION DES MIDDLEWARES
# ==========================================

def add_middleware(app: FastAPI):
    """
    Configure les middlewares de l'application.
    L'ordre est important : CORS d'abord, puis logging/rate-limit.
    """

    app.add_middleware(
        CORSMiddleware,

        allow_origins=[
            "https://voixafricaine.netlify.app",
            "http://localhost:3000",
        ],

        allow_credentials=True,

        allow_methods=["*"],

        allow_headers=["*"],
    )

    # Logging + rate limiting (ajouté en dernier = exécuté en premier)
    app.add_middleware(RequestLoggingMiddleware)

