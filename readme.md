# Voix Africaine — API

API REST de gestion de livres audio africains : livres, chapitres, upload et
validation d'audio, lectures et commentaires horodatés (timecodes).

> **Stack** : Python 3.11+ · FastAPI · Motor/MongoDB · Pydantic v2 · JWT
> (python-jose) · Passlib/bcrypt · Cloudinary · pydub · Uvicorn.

## Fonctionnalités

- Authentification JWT (rôles `admin` / `user`), compte admin créé au premier
  démarrage (idempotent, `app/bootstrap.py`).
- Livres et chapitres : création, publication, pagination `skip`/`limit`.
- Upload audio sur Cloudinary ; validation et suppression réservées aux admins.
- Traçage des **lectures** et **commentaires** horodatés par chapitre.
- Rate limiting, logging structuré (JSON en prod), CORS, sonde `/health`.

## Structure

```text
main.py                 # app FastAPI : lifespan, logging, routeurs, middlewares
app/
├── config.py           # settings (pydantic-settings, lit le .env)
├── database.py         # client Motor + init_db()
├── bootstrap.py        # index MongoDB + admin par défaut (idempotent)
├── auth_utils.py       # bcrypt, JWT, get_current_user, require_admin
├── middleware.py       # CORS (+ rate limiting / logging)
├── models.py           # modèles Pydantic
├── routes/             # /auth /livres /chapitres /lectures /commentaires
└── services/           # logique métier + accès MongoDB
scripts/                # init_db (versionné) ; scripts de test/dev en local uniquement
                        # (smoke_test, test_audio_flow, import_chevre, run_dev.sh :
                        # non versionnés, voir .gitignore)
```

## Installation

Prérequis : Python 3.11+, MongoDB local (`mongod`), `ffmpeg` (utilisé par
`pydub`), un compte Cloudinary (uniquement pour l'upload audio).

```bash
python -m venv env && source env/bin/activate
pip install -r requirements.txt
cp .env.example .env      # puis renseigner vos valeurs
env/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Documentation : Swagger sur `/docs`, Redoc sur `/redoc`, schéma sur
`/openapi.json`, sonde de santé sur `/health`.

### Variables d'environnement (`.env`)

Le `.env` (non versionné) est **prioritaire** sur les variables du shell.
Modèle commenté : `.env.example`.

| Variable | Rôle |
|----------|------|
| `SECRET_KEY` | Signature des JWT — générer : `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` | Paramètres JWT (`HS256`, `30`) |
| `MONGO`, `MONGO_DB_NAME` | Connexion MongoDB (ex. `mongodb://localhost:27017`, `voix_africaine`) |
| `DEFAULT_ADMIN_EMAIL` / `DEFAULT_ADMIN_PASSWORD` / `DEFAULT_ADMIN_FULL_NAME` | Compte admin créé au premier lancement — **choisir ses propres valeurs** |
| `CLOUDINARY_CLOUD_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET` | Upload audio |
| `RATE_LIMIT_*`, `LOG_LEVEL`, `LOG_FORMAT`, `MAX_AUDIO_UPLOAD_MB` | Sécurité / logs / upload (voir `.env.example`) |

> ⚠️ Utiliser un **domaine email valide** : les domaines réservés (`*.local`,
> `*.test`, `*.example`) sont rejetés par `email-validator` et provoquent un
> HTTP 500 sur `GET /auth/me`.

> ⚠️ Après le premier démarrage, **changer le mot de passe** de
> l'administrateur créé depuis les variables `DEFAULT_ADMIN_*`.

### Initialiser la base

```bash
env/bin/python -m scripts.init_db   # index + admin par défaut (idempotent)
```

L'admin est aussi créé automatiquement au démarrage de l'API : si le compte
existe déjà, son mot de passe n'est jamais écrasé.

### Vérifications de bout en bout

```bash
env/bin/python -m scripts.smoke_test        # livres → chapitres → commentaires
env/bin/python -m scripts.test_audio_flow   # upload → Cloudinary → suppression
```

> ℹ️ `smoke_test.py` et `test_audio_flow.py` sont des **scripts locaux** (non
> versionnés, voir `.gitignore`) : ils contiennent des identifiants de test et
> ne doivent jamais être déployés ni commités.

## API (aperçu)

| Route | Description |
|-------|-------------|
| `/auth` | `POST /register`, `POST /token`, `GET /me`, `GET /{user_id}`, … |
| `/livres` | CRUD livres, `GET /public/` paginé |
| `/chapitres` | CRUD chapitres, upload / validation / suppression d'audio |
| `/lectures` | traçage des écoutes (`POST /`, `GET /user/{user_id}`) |
| `/commentaires` | commentaires horodatés par chapitre |
| `/health` | sonde de santé (Render) |

## Déploiement

Blueprint `render.yaml` : runtime Docker (voir `Dockerfile`), les secrets sont
définis **uniquement dans le dashboard** du service (clés en `sync: false`) —
aucun fichier `.env` n'est déployé.

Origines CORS : configurées dans `app/middleware.py` (localhost + origine du
front déployé).

## Sécurité

- Ne jamais versionner `.env` : couvert par `.gitignore`, seul `.env.example`
  (sans secrets) est suivi.
- Secrets (JWT, MongoDB, Cloudinary) : dashboard Render uniquement, jamais dans
  le code ni dans les fichiers YAML suivis.
- En production, surcharger `DEFAULT_ADMIN_*` via le dashboard pour ne pas
  conserver les valeurs par défaut.
