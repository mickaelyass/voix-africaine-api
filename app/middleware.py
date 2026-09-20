
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def add_middleware(app: FastAPI):
    """
    Configure les middlewares de l'application.
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

