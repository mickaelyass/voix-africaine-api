import cloudinary

from app.config import settings


def init_cloudinary():
    """Initialise la connexion a Cloudinary."""
    settings.require_runtime_settings()
    assert settings.CLOUDINARY_CLOUD_NAME is not None
    assert settings.CLOUDINARY_API_KEY is not None
    assert settings.CLOUDINARY_API_SECRET is not None

    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )

    print("Cloudinary configure avec succes")
