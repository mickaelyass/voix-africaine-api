
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # ==========================================
    # APPLICATION
    # ==========================================

    SECRET_KEY: str
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

    MONGO: str
    MONGO_DB_NAME: str = "voix_africaine"


    # ==========================================
    # GOOGLE AUTH
    # ==========================================

    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None


    # ==========================================
    # CLOUDINARY
    # ==========================================

    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str


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


settings = Settings()

