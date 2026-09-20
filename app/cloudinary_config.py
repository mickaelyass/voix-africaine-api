
import cloudinary

from app.config import settings


def init_cloudinary():
    """
    Initialise la connexion à Cloudinary.
    """

    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )

    print("✅ Cloudinary configuré avec succès")
