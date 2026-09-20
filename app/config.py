
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

