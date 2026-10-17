
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # ==========================================
    # APPLICATION
    # ==========================================

    SECRET_KEY: Optional[str] = None
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    API_PREFIX: str = "/api"


    # ==========================================
    # ADMIN PAR DÉFAUT (bootstrap — surcharger via variables d'environnement)
    # En production, renseigner DEFAULT_ADMIN_EMAIL et
    # DEFAULT_ADMIN_PASSWORD dans le dashboard (aucun .env envoyé).
    # ==========================================

    DEFAULT_ADMIN_EMAIL: str = "admin@voixafricaine.com"
    DEFAULT_ADMIN_PASSWORD: str = "change-me-in-production"
    DEFAULT_ADMIN_FULL_NAME: str = "Administrateur"


    # ==========================================
    # MONGODB
    # ==========================================

    MONGO: Optional[str] = None
    MONGO_DB_NAME: str = "voix_africaine"

    # Pool de connexions MongoDB — réduit la latence des requêtes répétées
    # en réutilisant les connexions plutôt que d'en ouvrir une par requête.
    MONGO_MAX_POOL_SIZE: int = 50
    MONGO_MIN_POOL_SIZE: int = 10
    MONGO_SERVER_SELECTION_TIMEOUT_MS: int = 5000
    MONGO_CONNECT_TIMEOUT_MS: int = 10000
    MONGO_SOCKET_TIMEOUT_MS: int = 20000


    # ==========================================
    # RATE LIMITING (sécurité)
    # ==========================================
    # Limite les requêtes par IP pour protéger contre le brute-force et le DDoS.
    # 0 = désactivé (utile en dev local).

    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_AUTH_ATTEMPTS: int = 5        # max tentatives /auth/token par fenêtre
    RATE_LIMIT_AUTH_WINDOW_SECONDS: int = 60  # fenêtre glissante (secondes)
    RATE_LIMIT_GLOBAL_REQUESTS: int = 120     # max requêtes globales par IP / fenêtre
    RATE_LIMIT_GLOBAL_WINDOW_SECONDS: int = 60


    # ==========================================
    # UPLOAD / TÉLÉVERSEMENT AUDIO
    # ==========================================

    MAX_AUDIO_UPLOAD_MB: int = 50            # taille max fichier audio (Mo)
    ALLOWED_AUDIO_EXTENSIONS: str = "mp3,wav,ogg,m4a,webm,flac"
    ALLOWED_AUDIO_MIME_TYPES: str = (
        "audio/mpeg,audio/wav,audio/x-wav,audio/ogg,audio/mp4,"
        "audio/x-m4a,audio/webm,audio/flac"
    )


    # ==========================================
    # GOOGLE AUTH
    # ==========================================

    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None


    # ==========================================
    # CLOUDINARY
    # ==========================================

    CLOUDINARY_CLOUD_NAME: Optional[str] = None
    CLOUDINARY_API_KEY: Optional[str] = None
    CLOUDINARY_API_SECRET: Optional[str] = None


    # ==========================================
    # LOGGING / OBSERVABILITÉ
    # ==========================================

    LOG_LEVEL: str = "INFO"                 # DEBUG, INFO, WARNING, ERROR
    LOG_FORMAT: str = "json"                # "json" (prod) ou "text" (dev)


    # ==========================================
    # PYDANTIC SETTINGS
    # ==========================================

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """
        Le fichier `.env` est prioritaire sur les variables d'environnement.

        Sans cet ordre explicite, pydantic-settings donne la priorité au
        shell : un `MONGO` ou un `SECRET_KEY` hérité de la session
        écraserait silencieusement la configuration locale du projet.
        En production (aucun `.env` présent), `dotenv_settings` est vide
        et les variables d'environnement sont utilisées normalement.
        """

        return (
            init_settings,
            dotenv_settings,
            env_settings,
            file_secret_settings,
        )

    def missing_runtime_vars(self) -> list[str]:
        """Variables obligatoires absentes pour faire tourner l'API."""
        required = {
            "SECRET_KEY": self.SECRET_KEY,
            "MONGO": self.MONGO,
            "CLOUDINARY_CLOUD_NAME": self.CLOUDINARY_CLOUD_NAME,
            "CLOUDINARY_API_KEY": self.CLOUDINARY_API_KEY,
            "CLOUDINARY_API_SECRET": self.CLOUDINARY_API_SECRET,
        }
        return [name for name, value in required.items() if not value]

    def require_runtime_settings(self) -> None:
        """
        Vérifie au DÉMARRAGE (pas à l'import) que les secrets sont présents.

        Levée après l'import : le build Render (pip install, collect static,
        etc.) n'importe plus en échec, tandis qu'un démarrage sans secrets
        échoue avec un message explicite au lieu d'une ValidationError
        pydantic obscure.
        """
        missing = self.missing_runtime_vars()
        if missing:
            raise RuntimeError(
                "Configuration incomplète — variables manquantes : "
                + ", ".join(missing)
                + ". Renseignez-les dans le dashboard Render "
                "(Service > Environment), sans fichier .env. "
                "Voir .env.example pour la liste complète."
            )


settings = Settings()

