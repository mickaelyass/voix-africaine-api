# Voix Africaine — API Backend

API REST de gestion de livres audio africains : livres, chapitres, upload et
validation d'audio, lectures et commentaires horodatés (timecodes).

> **Stack** : Python 3.12 · FastAPI · Motor/MongoDB Atlas · Pydantic v2 ·
> JWT (python-jose) · Passlib/bcrypt · Cloudinary · pydub · Uvicorn.

---

## 1. Aperçu

Le projet est un **backend uniquement** (aucun frontend, pas de `package.json`).
Il expose une API JSON documentée automatiquement par FastAPI (Swagger sur
`/docs`, ReDoc sur `/redoc`, schéma sur `/openapi.json`).

L'objectif fonctionnel est de permettre à des lecteurs/voix off de publier des
**livres** découpés en **chapitres** dotés d'un **audio** (uploadé sur
Cloudinary), l'audio pouvant être **validé par un administrateur**, et aux
utilisateurs d'écouter (tracer des **lectures**) et de commenter l'audio à une
**position temporelle** donnée.

---

## 2. Architecture

```
voix-africaine-api/
├── main.py                     # Point d'entrée FastAPI : app, startup, routeurs, middlewares
├── requirements.txt            # Dépendances Python
├── .env                        # Configuration locale (gitignoré)
├── .env.example                # Modèle de configuration (versionnable)
├── scripts/
│   ├── init_db.py              # Index MongoDB + admin par défaut (hors API)
│   ├── smoke_test.py           # Test de fumée de bout en bout
│   ├── test_audio_flow.py      # Test de non-régression : enregistrement audio → Cloudinary
│   └── run_dev.sh              # Lancement de l'API en développement
└── app/
    ├── config.py               # Settings (pydantic-settings) lisant .env
    ├── database.py             # Client Motor async + db + init_db() (ping)
    ├── bootstrap.py            # Index MongoDB + admin par défaut (idempotent)
    ├── cloudinary_config.py     # init_cloudinary()
    ├── auth_utils.py           # Hachage bcrypt, JWT, get_current_user, require_admin
    ├── middleware.py           # CORS
    ├── models.py               # Modèles Pydantic (User, Livre, Chapitre, Lecture, Commentaire)
    ├── routes/                 # Couche HTTP (contrôleurs)
    │   ├── auth.py             # /auth
    │   ├── livres.py           # /livres
    │   ├── chapitres.py        # /chapitres
    │   ├── lectures.py         # /lectures
    │   └── comment.py          # /commentaires
    └── services/               # Couche métier / accès MongoDB
        ├── auth_service.py
        ├── livre_service.py
        ├── chapitre_service.py
        ├── lecture_service.py
        └── commentaire_service.py
```

### Organisation en couches

| Couche | Rôle | Fichiers |
|--------|------|----------|
| **Entrée** | Instancie `FastAPI`, branche les routeurs et middlewares | `main.py` |
| **Routes** | Déclarent les endpoints, l'authentification et les `response_model` | `app/routes/*.py` |
| **Services** | Logique métier + requêtes MongoDB | `app/services/*.py` |
| **Données** | Schémas Pydantic | `app/models.py` |
| **Transverse** | Config, DB, Cloudinary, auth, CORS | `app/config.py`, `app/database.py`, `app/cloudinary_config.py`, `app/auth_utils.py`, `app/middleware.py` |

### Collections MongoDB

| Collection | Contenu | Clé d'identification |
|-----------|---------|----------------------|
| `users` | Utilisateurs (email, `hashed_password`, `full_name`, `role`, `disabled`, `google_id`, `created_at`) | `_id` (ObjectId) |
| `livres` | Livres (`id` **string fourni par le client**, titre, auteur, description, `is_public`) | `id` (string) |
| `chapitres` | Chapitres (`id` string, `livre_id`, `titre`, `numero`, `contenu_texte`, `audio_url`, `audio_public_id`, `duration_sec`, `is_public`, `created_by`, `audio_validated*`) | `id` (string) |
| `lectures` | Progression d'écoute (`user_id`, `chapitre_id`, `date_lecture`, `is_completed`, `listened_seconds`) | couple `(user_id, chapitre_id)` |
| `commentaires` | Commentaires (`contenu`, `timestamp`, `chapitre_id`, `user_id`, `created_at`, `updated_at`, `is_public`) | `_id` (ObjectId) |

### Authentification

- Mot de passe haché en **bcrypt** (`passlib`).
- **JWT** HS256 signé avec `SECRET_KEY`, payload `{"sub": <user_id>, "exp": ...}`,
  durée `ACCESS_TOKEN_EXPIRE_MINUTES`.
- Endpoint token : `POST /auth/token` (form `OAuth2PasswordRequestForm`).
- Dépendances de sécurité : `get_current_user`, `get_current_active_user`,
  `require_admin` (contrôle du rôle `admin`).
---

## 3. Fonctionnalités implémentées

### 3.1 Authentification & utilisateurs

| Fonctionnalité | Détail | Endpoint |
|----------------|--------|----------|
| Inscription | Création d'un utilisateur (email unique, mot de passe ≥ 8 caractères), rôle `user` par défaut, réponse publique sans mot de passe | `POST /auth/register` |
| Connexion | Vérification email/mot de passe et émission d'un token JWT Bearer | `POST /auth/token` |
| Profil courant | Retourne l'utilisateur authentifié (id, email, full_name, role, created_at) | `GET /auth/me` |
| Profil public | Récupère les infos publiques d'un utilisateur par id | `GET /auth/{user_id}` |
| Liste des utilisateurs | Liste tous les utilisateurs (incluant le hash du mot de passe — voir recommandations) | `GET /auth/` |
| Rôles | Enum `user` / `admin` + dépendance `require_admin` | — |
| Comptes désactivés | Champ `disabled` vérifié par `get_current_active_user` | — |
| Google OAuth | **Stub** : la route existe mais le corps est vide (`pass`), non fonctionnelle | `POST /auth/google-auth` |

### 3.2 Gestion des livres

| Fonctionnalité | Détail | Endpoint |
|----------------|--------|----------|
| Créer un livre | Réservé aux admins ; vérifie l'unicité de l'`id` **et** du `titre` | `POST /livres/` |
| Lister les livres publics | Public, sans authentification, renvoie les livres `is_public == true` | `GET /livres/public/` |
| Consulter un livre | Authentifié ; un livre privé n'est visible que par un admin | `GET /livres/{livre_id}` |
| Modifier un livre | Réservé aux admins | `PUT /livres/{livre_id}` |
| Supprimer un livre | Réservé aux admins | `DELETE /livres/{livre_id}` |
| Visibilité | Champ `is_public` par livre | — |

### 3.3 Gestion des chapitres

| Fonctionnalité | Détail | Endpoint |
|----------------|--------|----------|
| Créer un chapitre | Authentifié ; vérifie l'existence du livre parent et l'unicité de `id` et du couple `(livre_id, numero)` ; enregistre `created_by` | `POST /chapitres/` |
| Consulter un chapitre public | Public ; renvoie un modèle épuré (`ChapitrePublic`) qui masque l'audio si non public | `GET /chapitres/public/{chapitre_id}` |
| Lister tous les chapitres publics | Public | `GET /chapitres/public` |
| Consulter un chapitre | Authentifié ; accès refusé si le chapitre est privé et que l'utilisateur n'est ni l'auteur ni admin | `GET /chapitres/{chapitre_id}` |
| Lister les chapitres d'un livre | Authentifié ; l'admin voit tout, les autres voient les chapitres publics ou les leurs | `GET /chapitres/livre/{livre_id}` |
| Basculer la visibilité | Auteur ou admin ; inverse `is_public` | `PATCH /chapitres/{chapitre_id}/toggle-public` |
| Supprimer un chapitre | Auteur ou admin | `DELETE /chapitres/{chapitre_id}` |

### 3.4 Audio des chapitres (Cloudinary)

| Fonctionnalité | Détail | Endpoint |
|----------------|--------|----------|
| Upload audio | Authentifié — **tout utilisateur connecté** peut enregistrer/envoyer l'audio d'un chapitre ; le champ multipart doit s'appeler **`file`** (sinon `422 Field required`) ; validation du type MIME (`webm`, `ogg`, `mpeg`, `wav`, `mp3`, `x-wav`) avec repli sur l'extension quand le navigateur n'annonce pas de type audio, refus des fichiers vides, upload Cloudinary sous `chapitres/{chapitre_id}/`, calcul de la durée via pydub (nécessite **ffmpeg**) | `PUT /chapitres/{chapitre_id}/upload-audio` |
| Verrou après validation | Un audio validé ne peut plus être remplacé ni supprimé (HTTP 403) | — |
| Validation admin | Réservé aux admins ; exige un audio existant, positionne `audio_validated`, `audio_validated_at`, `audio_validated_by` | `PATCH /chapitres/{chapitre_id}/validate-audio` |
| Suppression audio | **Réservée aux administrateurs** (HTTP 403 pour les autres) ; interdite si l'audio est validé ; supprime le fichier Cloudinary **et** réinitialise les champs audio en base (`audio_url`, `audio_public_id`, `audio_resource_type`, `duration_sec`, validation) | `DELETE /chapitres/{chapitre_id}/audio` |
| Confidentialité audio | `ChapitrePublic` ne renvoie `audio_url` que si `is_public` est vrai | — |

### 3.5 Lectures (suivi d'écoute)

| Fonctionnalité | Détail | Endpoint |
|----------------|--------|----------|
| Enregistrer une lecture | Authentifié ; vérifie l'existence du chapitre et l'accès (public ou auteur) ; **upsert** sur `(user_id, chapitre_id)` ; le `user_id` est forcé à l'utilisateur courant | `POST /lectures/` |
| Historique d'un utilisateur | Soi-même ou admin uniquement | `GET /lectures/user/{user_id}` |
| Progression | Champs `is_completed` et `listened_seconds` | — |

### 3.6 Commentaires horodatés

| Fonctionnalité | Détail | Endpoint |
|----------------|--------|----------|
| Créer un commentaire | Authentifié (token requis) ; contenu, `timestamp` (position dans l'audio), `chapitre_id`, `user_id` ; réponse enrichie des infos publiques de l'auteur | `POST /commentaires/` |
| Lister par chapitre | Authentifié ; tri du plus récent au plus ancien | `GET /commentaires/` |
| Lister tous les commentaires | Agrégation MongoDB `$lookup` vers `users`, filtre `is_public` | `GET /commentaires/all` |
| Chapitre + commentaires | Renvoie un chapitre avec ses commentaires imbriqués | `GET /commentaires/chapitre/{chapitre_id}` |
| Supprimer un commentaire | Auteur ou admin | `DELETE /commentaires/{comment_id}` |
| Modèle public | `CommentairePublic` expose `contenu`, `timestamp`, `user_info`, dates | — |

### 3.7 Transverse

- **CORS** configuré pour `https://voixafricaine.netlify.app` et `http://localhost:3000`.
- **Documentation auto** : `/docs`, `/redoc`, `/openapi.json`.
- **Startup** : initialisation Cloudinary, `ping` MongoDB, création des index et
  de l'administrateur par défaut (`app/bootstrap.py`).
- **Docker** : **retiré du projet**. Les fichiers `Dockerfile` et
  `docker-compose.yml` ont été supprimés du suivi Git (`git rm --cached`).
  Le développement se fait avec un `mongod` local.

---

## 4. Installation et lancement

### Prérequis

- Python 3.11+ (développé avec 3.12)
- **MongoDB local** (`mongod`) — le projet n'utilise plus MongoDB Atlas
- Un compte Cloudinary (nécessaire uniquement pour l'upload audio)
- `ffmpeg` installé sur la machine (utilisé par `pydub` pour calculer la durée audio)

### Variables d'environnement

Un seul fichier de configuration : **`.env` à la racine du projet** (gitignoré).
Partir du modèle fourni :

```bash
cp .env.example .env
```

| Variable | Rôle | Valeur locale |
|----------|------|---------------|
| `SECRET_KEY` | Signature des JWT | à régénérer : `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `ALGORITHM` / `ACCESS_TOKEN_EXPIRE_MINUTES` | Paramètres JWT | `HS256` / `30` |
| `MONGO` | Connexion MongoDB | `mongodb://localhost:27017` |
| `MONGO_DB_NAME` | Nom de la base | `voix_africaine` |
| `DEFAULT_ADMIN_EMAIL` | Admin créé au premier lancement | `admin@voixafricaine.com` |
| `DEFAULT_ADMIN_PASSWORD` | Mot de passe de cet admin | `Admin@Voix2026` |
| `DEFAULT_ADMIN_FULL_NAME` | Nom affiché | `Administrateur` |
| `CLOUDINARY_*` | Upload audio | à renseigner |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth (stub) | optionnel |

> **Le `.env` est prioritaire sur les variables d'environnement du shell**
> (`Settings.settings_customise_sources`). Sans cet ordre explicite, un `MONGO`
> ou un `SECRET_KEY` exporté dans la session écraserait silencieusement la
> configuration du projet — cause d'un bug de connexion rencontré en local.

> ⚠️ **Domaine email valide obligatoire** : `email-validator` rejette les
> domaines réservés (`*.local`, `*.test`, `*.invalid`, `*.example`). Utiliser un
> TLD réel, sinon `GET /auth/me` renvoie `HTTP 500` (violation du
> `response_model=UserPublic`).

### Initialiser la base MongoDB locale

```bash
# 1. Vérifier que mongod écoute
mongosh --quiet --eval 'db.adminCommand({ping: 1})'

# 2. Créer les index + l'administrateur par défaut
env/bin/python -m scripts.init_db
```

L'administrateur par défaut est **aussi** créé automatiquement au premier
démarrage de l'API. Les deux chemins passent par `app/bootstrap.py` et sont
idempotents : si le compte existe déjà, son mot de passe n'est jamais écrasé.

**Administrateur créé par défaut**

| Champ | Valeur |
|-------|--------|
| Email | `admin@voixafricaine.com` |
| Mot de passe | `Admin@Voix2026` |
| Rôle | `admin` |

> ⚠️ Ces valeurs viennent de `.env` : changez le mot de passe juste après la
> première connexion.

### Lancer l'API

```bash
./scripts/run_dev.sh              # http://127.0.0.1:8000, rechargement auto
PORT=9000 ./scripts/run_dev.sh    # port personnalisé
```

Puis ouvrir <http://localhost:8000/docs>.

### Vérifier de bout en bout

```bash
env/bin/python -m scripts.smoke_test        # cycle livres → chapitres → commentaires
env/bin/python -m scripts.test_audio_flow   # flux audio : enregistrement → Cloudinary → suppression
```

Le premier test s'authentifie avec l'admin par défaut, déroule le cycle
livres → chapitres → commentaires, contrôle le préflight CORS depuis
`http://localhost:3000`, puis supprime les données qu'il a créées. Les défauts
déjà connus (section 5) sont signalés par `⚠️` sans faire échouer la suite.

Le second vérifie les règles métier de l'**enregistrement vocal** : un
utilisateur de rôle `user` crée un chapitre et envoie son audio (champ
multipart **`file`**), l'audio est relisible ensuite, seuls les
administrateurs peuvent **supprimer** ou **valider** l'audio, et la
suppression efface réellement le fichier Cloudinary (y compris les audios
historiques stockés sous l'ancien chemin dupliqué). Il effectue de vrais
appels Cloudinary (envoi puis suppression d'un WAV d'une seconde) et se
nettoie lui-même.

### Docker

Docker a été **retiré du projet** : plus de `Dockerfile`, plus de
`docker-compose.yml`, plus de secrets en clair dans un fichier versionné.
Le développement et les tests se font sur un `mongod` local.

---

## 5. Problèmes identifiés dans le code actuel

Ces points sont vérifiables dans le code ; certains sont des **bugs bloquants**,
d'autres des **failles de sécurité**.

### 🔴 Bugs bloquants

1. **`GET /commentaires/all` renvoie systématiquement une erreur 500.** *(corrigé)*
   La projection d'agrégation ne renvoie que `id`, `email`, `full_name` pour
   `user_info`, alors que `UserPublic` exige aussi `role` et `created_at`
   (`app/services/commentaire_service.py`, `app/models.py`). Vérifié
   expérimentalement : `ValidationError` → transformée en HTTP 500.

   > ✅ **Corrigé** : le `$lookup` convertit désormais `user_id` (string) en
   > `ObjectId` via `$convert`, la projection renvoie `role` et `created_at`,
   > et l'absence de commentaire donne une liste vide (`200 []`) au lieu d'une
   > 404 transformée en 500.

2. **`GET /commentaires/chapitre/{id}` ne renvoie jamais les commentaires.** *(corrigé)*
   `ChapitreWithComments` hérite du `@model_serializer` de `ChapitrePublic`,
   qui ne sérialise que 6 champs et **ignore le champ `commentaires`**.
   Vérifié expérimentalement : `model_dump()` ne contient pas `commentaires`.

   > ✅ **Corrigé** : `ChapitreWithComments` redéfinit son propre
   > `@model_serializer` et expose `commentaires` (plus `contenu_texte`,
   > `is_public`, `audio_validated`).

3. **`DELETE /commentaires/{id}` échoue toujours.** *(corrigé)*
   `comment.py` fait `current_user.id` alors que `current_user` est un `dict` →
   `AttributeError`, capturée et transformée en HTTP 400.

   > ✅ **Corrigé** : la route utilise `current_user["_id"]`, retourne `204` en
   > cas de succès, `404` si le commentaire n'existe pas et `403` si
   > l'utilisateur n'est ni l'auteur ni administrateur.

4. **`GET /commentaires/chapitre/{id}` utilise `ObjectId(chapitre_id)`** alors que *(corrigé)*
   le reste de l'API identifie les chapitres par leur champ `id` (string fourni
   par le client). Les identifiants sont donc incohérents entre endpoints.

   > ✅ **Corrigé** : le chapitre est recherché par `{"id": chapitre_id}` et
   > `POST /commentaires/` vérifie l'existence du chapitre par ce même champ.

5. **Le contrôle de propriété des chapitres ne fonctionne pas pour les non-admins.**
   - `toggle_chapitre_public` compare `str(created_by)` (string) à
     `current_user["_id"]` (ObjectId) → toujours faux.
   - `get_chapitres_du_livre` filtre `{"created_by": current_user["_id"]}`
     (ObjectId) alors que `created_by` est stocké en string.
   Résultat : un auteur ne peut ni basculer ni retrouver ses propres chapitres.

### 🔴 Failles de sécurité

6. **`GET /auth/` exposait les hashs de mots de passe** *(corrigé)* :
   (`response_model=list[UserInDB]` contenait `hashed_password`).

   > ✅ **Corrigé** : `GET /auth/` exige `require_admin` et renvoie
   > `list[UserPublic]` (sans hash).

7. **`GET /auth/{user_id}` exposait l'email d'un utilisateur** *(corrigé)* →
   énumération d'utilisateurs / fuite de données personnelles.

   > ✅ **Corrigé** : `GET /auth/{user_id}` n'est accessible qu'à
   > l'utilisateur lui-même ou à un administrateur (403 sinon).

8. **`POST /commentaires/` accepte un `user_id` arbitraire dans le corps** *(corrigé)* :
   n'importe quel porteur de token peut poster un commentaire au nom d'un autre
   utilisateur (usurpation d'identité).

   > ✅ **Corrigé** : `POST /commentaires/` déduit l'auteur de
   > `current_user["_id"]` ; `CommentInput.user_id` est déprécié et ignoré
   > (le frontend ne l'envoie plus).

9. **`SECRET_KEY=YASSEGOUNGBE`** et **identifiants MongoDB/Cloudinary réels
   présents dans `docker-compose.yml`** (versionné dans Git) et dans les `.env`
   locaux. Les secrets Cloudinary et le mot de passe Mongo doivent être
   **considérés comme compromis et rotés immédiatement**.

10. **`POST /chapitres/` n'impose aucune règle d'autorisation** : tout utilisateur
    authentifié peut créer un chapitre dans n'importe quel livre.

11. **Aucune limite/validation sur la taille du fichier audio** uploadé
    (risque de saturation mémoire/stockage).

12. **Injection / XSS** : le contenu des commentaires et chapitres n'est ni
    échappé ni nettoyé côté serveur (impact si le frontend l'injecte en HTML).

### 🟠 Incohérences fonctionnelles

13. **`Chapitre.id` et `Livre.id` sont obligatoires et fournis par le client**
    alors que le reste de l'API (users, commentaires, lectures) utilise les
    `ObjectId` MongoDB → deux conventions d'identifiants cohabitent.

14. **`get_commentaires_for_chapitre` ignore `skip`/`limit`** et applique *(corrigé)*
    silencieusement `.limit(10)`.

    > ✅ **Corrigé** : `.skip(skip).limit(limit)` est appliqué (valeurs bornées),
    > et les routes exposent `skip`/`limit` (y compris `GET /commentaires/all`).

15. **`resource_type` incohérent côté Cloudinary** : upload en `auto`, suppression
    en `video` → risque de fichiers orphelins.

16. **Aucun index MongoDB** défini (`users.email`, `livres.id`, `chapitres.id`,
    `chapitres.(livre_id, numero)`, `lectures.(user_id, chapitre_id)`,
    `commentaires.chapitre_id`) → performances dégradées et risque de doublons
    en cas d'accès concurrent.

17. **`GET /chapitres/public` renvoie 404 s'il n'y a aucun chapitre public**
    au lieu d'une liste vide.

18. **`@app.on_event("startup")` est déprécié** dans les versions récentes de
    FastAPI (préférer le `lifespan`).

19. **`POST /auth/google-auth` est un stub vide** (non fonctionnel).

20. **Aucun test automatisé** n'existe (`pytest` est installé mais aucune suite),
    ni `conftest.py`, ni `tests/`.
### 5.1 Correctifs appliqués — CRUD commentaires

Les points 1, 2, 3, 4, 8 et 14 ont été corrigés. Détail des changements :

| Fichier | Correction |
|---------|------------|
| `app/routes/comment.py` | `DELETE` utilise `current_user["_id"]` (plus d'`AttributeError`) ; `POST` s'appuie sur `get_current_active_user` et ignore `user_id` ; `GET /` exige `chapitre_id` et propage `skip`/`limit` ; `GET /all` accepte `skip`/`limit` ; les `HTTPException` ne sont plus écrasées en 400/500 |
| `app/services/commentaire_service.py` | jointure `$lookup` avec `$convert` string → ObjectId (le `user_id` stocké en string ne matchait jamais `users._id`) ; projection complète de `UserPublic` (`role`, `created_at`) ; liste vide au lieu de 404 ; pagination réelle ; recherche du chapitre par `{"id": ...}` ; création refusée si le chapitre n'existe pas ; comparaison des identifiants en `str` |
| `app/models.py` | `CommentairePublic.user_info` devient optionnel (auteur supprimé) et expose `chapitre_id` ; `ChapitreWithComments` redéfinit son `@model_serializer` pour ne plus perdre `commentaires` |
| `../voix-africaine-web/src/pages/ListeChapitres.jsx` | n'envoie plus `user_id` ; garde `commentaire.user_info?.full_name` ; bouton « Supprimer » pour l'auteur ou un admin ; remontée des erreurs API |
| `scripts/smoke_test.py` | les 3 bugs bloquants ne sont plus marqués « échec connu » ; couverture ajoutée : auteur déduit du token, `user_id` forgé ignoré, pagination, `/all`, `/chapitre/{id}`, `DELETE` 204 puis 404 |

Résultat du test de fumée après correction : **23/23 vérifications réussies**.

### 5.2 Correctifs appliqués — enregistrement audio (Cloudinary)

L'enregistrement au micro, puis l'envoi vers Cloudinary, ne fonctionnaient pas.
Quatre causes ont été identifiées et corrigées :

| # | Cause | Correctif |
|---|-------|-----------|
| 1 | **Frontend** : `AudioRecorderUploader.jsx` envoyait le fichier dans un champ multipart `audio` alors que FastAPI attend `file` → l'API répondait `422 {"detail":[{"type":"missing","loc":["body","file"]}]}` et l'audio n'atteignait **jamais** Cloudinary. | `formData.append('file', ...)` + messages d'erreur explicites (401 / 403 / 422). |
| 2 | **Backend** : `cloudinary.uploader.upload()` recevait à la fois `folder="chapitres/{id}"` **et** un `public_id` contenant déjà ce dossier → Cloudinary stockait le fichier sous `chapitres/{id}/chapitres/{id}/{uuid}` alors que `audio_public_id` valait `chapitres/{id}/{uuid}`. La suppression admin ne retrouvait donc plus le fichier (fichiers orphelins). | Le dossier n'est porté que par le `public_id` ; `audio_public_id` et le nouveau champ `audio_resource_type` sont désormais relus depuis la **réponse** de Cloudinary. |
| 3 | **Backend** : `supprimer_audio_chapitre` cherchait le fichier au mauvais chemin et forçait le type de ressource. | Suppression avec le `resource_type` stocké, plus repli automatique sur l'ancien chemin dupliqué pour nettoyer les audios déjà en base (les 7 fichiers existants étaient dans ce cas). |
| 4 | **Frontend** : après un envoi réussi, `ListeChapitres.jsx` conservait une copie périmée du chapitre (`chapitreActif`) : le lecteur audio n'apparaissait pas et il fallait recliquer sur le chapitre pour réécouter l'enregistrement. | Le chapitre sélectionné est resynchronisé avec la liste rafraîchie ; l'audio apparaît dès la fin de l'envoi. |

Règles métier confirmées par `scripts/test_audio_flow.py` :

- **tout utilisateur connecté** (`role: user`) peut créer un chapitre, puis
  enregistrer/envoyer et **réécouter** son audio ;
- la **suppression de l'audio** et la **validation** sont **réservées à
  l'admin** (HTTP 403 pour les autres) ;
- la suppression admin efface **réellement** le fichier Cloudinary, y compris
  les audios historiques stockés sous l'ancien chemin dupliqué.

Pour que l'enregistrement soit atteignable depuis l'interface, le bouton
« + Ajouter un chapitre » de `LivreDetail.jsx` est désormais visible pour tout
utilisateur connecté (le backend l'autorisait déjà). Les actions de
suppression, elles, restent masquées pour les non-administrateurs.

Résultat : **27/27 vérifications réussies** (`env/bin/python -m scripts.test_audio_flow`).

---

## 6. Recommandations d'amélioration

Organisées par priorité (impact / effort). Les trois premières catégories
constituent la « dette critique » à traiter en premier.

### 6.1 Sécurité (priorité 1)

1. **Révoquer et régénérer tous les secrets exposés.**
   - Changer le mot de passe du cluster MongoDB Atlas et l'API Secret Cloudinary
     (ils sont présents dans l'historique Git via `docker-compose.yml`).
   - Purger l'historique : `git filter-repo --path docker-compose.yml --invert-paths`
     puis `git push --force-with-lease` (prévenir les collaborateurs).
   - Générer un vrai secret : `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
   - Ne jamais versionner de `.env` ; fournir un `.env.example` documenté.

2. **Protéger les routes d'administration (`auth.py`).**
   ```python
   from app.auth_utils import require_admin

   @router.get("/", response_model=list[UserPublic])   # <- pas UserInDB
   async def alluser(current_user: dict = Depends(require_admin)):
       return await get_all_user()

   @router.get("/{user_id}", response_model=UserPublic)
   async def get_user(user_id: str, current_user: dict = Depends(get_current_user)):
       return await _get_user_public_info(user_id)
   ```
   Ne jamais exposer `hashed_password` : bannir `UserInDB` des `response_model`.

3. **Déduire `user_id` du token, jamais du corps de la requête.**
   ```python
   class CommentInput(BaseModel):
       contenu: str = Field(..., min_length=1, max_length=1000)
       timestamp: float = Field(0.0, ge=0)
       chapitre_id: str

   @router.post("/", response_model=CommentairePublic)
   async def create_comment(
       comment_input: CommentInput,
       current_user: dict = Depends(get_current_active_user),
   ):
       return await CommentaireService.create_commentaire(
           comment_input, str(current_user["_id"])
       )
   ```

4. **Corriger les contrôles de propriété** en comparant des strings partout :
   ```python
   is_owner = str(chapitre.get("created_by")) == str(current_user["_id"])
   query = {"livre_id": livre_id,
            "$or": [{"is_public": True}, {"created_by": str(current_user["_id"])}]}
   ```

5. **Ajouter des limites d'upload** : taille maximale (ex. 25 Mo), vérification du
   contenu réel (magic bytes) en plus du MIME client, et quota par utilisateur.

6. **Activer la sécurité HTTP** : `fastapi-limiter` (rate limiting sur `/auth/token`),
   en-têtes de sécurité (HSTS, `X-Content-Type-Options`), journal d'audit des
   actions admin, et origines CORS pilotées par variables d'environnement plutôt
   que codées en dur.

7. **Renforcer l'authentification** : refresh tokens, rotation, blacklist JWT sur
   déconnexion, validation `aud`/`iss`, et rendre `POST /auth/google-auth`
   fonctionnel (vérification de l'`id_token` Google).

### 6.2 Corrections fonctionnelles (priorité 2)

8. **Corriger le sérialiseur de `ChapitreWithComments`** : ne pas hériter du
   `model_serializer` restrictif de `ChapitrePublic` ; construire la réponse
   explicitement.
   ```python
   class ChapitreWithComments(BaseModel):
       chapitre: ChapitrePublic
       commentaires: list[CommentairePublic] = []
   ```

9. **Compléter la projection d'agrégation** de `get_all_commentaires` avec
   `role` et `created_at`, ou assouplir `UserPublic` (`role`/`created_at`
   optionnels) pour éviter le HTTP 500.

10. **Utiliser `model_dump()` au lieu de `.dict()`** (déprécié en Pydantic v2)
    dans `livre_service.py` et `chapitre_service.py`.

11. **Unifier l'identification des entités** : soit tout en `ObjectId` (et
    `str()` uniquement à la frontière de l'API), soit tout en identifiant métier.
    Recommandé : laisser MongoDB générer `_id` et exposer un champ `id` calculé
    via `@model_serializer`, avec la même convention pour livres, chapitres,
    commentaires et lectures.

12. **Respecter `skip`/`limit`** dans `get_commentaires_for_chapitre` et
    harmoniser la pagination sur tous les endpoints de liste.

13. **Aligner le `resource_type` Cloudinary** entre upload (`auto`) et suppression
    (`video`), et stocker `resource_type` en base pour pouvoir supprimer correctement.

14. **Gérer proprement les listes vides** : renvoyer `[]` (HTTP 200) plutôt qu'un 404.

15. **Fermer les fuites de données** : la suppression d'un chapitre/livre doit
    cascader (audio Cloudinary, commentaires, lectures) ou être bloquée ;
    `delete_livre` actuellement ne nettoie rien.
### 6.3 Robustesse et qualité (priorité 3)

16. **Ajouter des tests** (`pytest` + `httpx.AsyncClient` + `mongomock-motor` ou
    une base de test dédiée) :
    - `tests/conftest.py` avec fixtures `app`, `client`, `admin_token`, `user_token` ;
    - tests d'authentification, de permissions (`require_admin`, propriété),
      d'upload audio (mock Cloudinary), de commentaires et de lectures.

17. **Structurer le projet** : ajouter les `__init__.py` manquants (`app/`,
    `app/routes/`, `app/services/`), un dossier `app/schemas/`, et centraliser
    les dépendances FastAPI dans `app/dependencies.py`.

18. **Créer les index MongoDB au démarrage** :
    ```python
    await db["users"].create_index("email", unique=True)
    await db["livres"].create_index("id", unique=True)
    await db["chapitres"].create_index("id", unique=True)
    await db["chapitres"].create_index([("livre_id", 1), ("numero", 1)], unique=True)
    await db["lectures"].create_index([("user_id", 1), ("chapitre_id", 1)], unique=True)
    await db["commentaires"].create_index([("chapitre_id", 1), ("created_at", -1)])
    ```

19. **Passer au `lifespan`** et fermer proprement le client Motor à l'arrêt :
    ```python
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_cloudinary()
        await init_db()
        await ensure_indexes()
        yield
        client.close()
    ```

20. **Configurer la journalisation** (`logging` ou `Logbook`) au lieu de `print()`,
    et logger les erreurs Cloudinary/Mongo avec leur contexte.

21. **Validation des entrées** : ajouter `min_length`/`max_length` partout
    (ex. `CommentInput.contenu`), valider `numero > 0`, et vérifier l'existence
    de `livre_id`/`chapitre_id` avant insertion.

22. **Enrichir l'OpenAPI** : `summary`, `description`, `responses` (`401`, `403`,
    `404`) et exemples pour chaque endpoint ; ajouter `openapi_tags` ordonné et
    les métadonnées (`contact`, `license`) dans `FastAPI()`.

### 6.4 DevOps et performance (priorité 4)

23. **Nettoyer le dépôt Git** :
    - supprimer `env/` du versionnement (il contient tout le virtualenv et des
      binaires — des dizaines de Mo) : `git rm -r --cached env/` puis ajouter
      `env/` au `.gitignore` ;
    - retirer les `__pycache__`/`*.pyc` déjà commités ;
    - ajouter `env/`, `.venv/`, `*.egg-info/`, `.pytest_cache/`, `.mypy_cache/`,
      `htmlcov/`, `.DS_Store` au `.gitignore`.

24. **Docker retiré (fait)** ✅ : `Dockerfile` et `docker-compose.yml` ont été
    supprimés du suivi Git (`git rm --cached`) — ils ne reviennent donc plus via
    un `git checkout`. Les secrets en clair qu'ils contenaient ont été sortis du
    répertoire de travail. Le projet tourne sur un `mongod` local.

    > Rappel : ces fichiers restent présents dans l'**historique** Git, avec les
    > identifiants MongoDB/Cloudinary. Les secrets doivent être **rotés** et
    > l'historique purgé (point 1). Si Docker redevient nécessaire plus tard,
    > repartir d'un `Dockerfile` propre : `python:3.12-slim`, utilisateur
    > non-root, `HEALTHCHECK`, variables injectées (jamais en dur), et un
    > `.dockerignore` contenant `env/`, `.git/`, `__pycache__/`, `*.pyc`,
    > `.env`, `.idea/`.

25. **Alléger `requirements.txt`** : retirer les paquets non utilisés
    (`starflyer`, `userbase`, `mongogogo`, `sf-mail`, `sf-babel`, `Paste`,
    `WTForms`, `google-cloud-storage`, `Logbook`…), séparer
    `requirements.txt` / `requirements-dev.txt` et épingler avec `pip-tools`.

26. **Observabilité** : endpoint `GET /health` (état Mongo + Cloudinary),
    métriques Prometheus (`prometheus-fastapi-instrumentator`) et traces
    OpenTelemetry.

27. **Performance** : pagination par curseur pour les grosses collections,
    remplacer la requête `users` par commentaire (problème N+1) par un seul
    `$lookup`, projeter `{"hashed_password": 0}` dans les lectures publiques, et
    mettre en cache (`cachetools`) les listes publiques.

28. **CI/CD** : GitHub Actions avec `ruff` (lint), `black` (format), `mypy`
    (typage), `pytest --cov` (tests + couverture), `pip-audit` (vulnérabilités),
    puis déploiement automatique.

### 6.5 Évolutions produit (roadmap suggérée)

29. **Vues agrégées** : nombre d'écoutes, durée moyenne d'écoute, favoris et
    notation par livre/chapitre.
30. **Recherche et filtres** : recherche plein texte (`$text` + index texte) sur
    titres, auteurs et descriptions ; filtres par langue, pays, catégorie.
31. **Génération audio** : intégration TTS (text-to-speech) pour convertir
    `contenu_texte` en audio, et STT pour générer automatiquement les timecodes.
32. **Modération** : statut des commentaires (`pending`/`approved`/`rejected`),
    signalement et outils admin de revue.
33. **Notifications** : email (validation d'audio, réponse à un commentaire) via
    une file asynchrone (Celery/RQ/ARQ).
34. **Temps réel** : WebSocket pour le fil de commentaires live pendant l'écoute.
35. **Droits plus fins** : rôles `user`, `auteur`, `moderateur`, `admin` avec
    permissions par ressource.
36. **Internationalisation** : messages d'erreur traduits et contenu multilingue
    (le projet cible l'Afrique francophone et anglophone).
---

## 7. Récapitulatif des priorités

| Priorité | Action | Impact |
|----------|--------|--------|
|  Immédiat | Rotation des secrets (Mongo, Cloudinary, JWT) + purge de l'historique Git | Critique |
| 🔥 Immédiat | ~~Sécuriser `GET /auth/`, `GET /auth/{id}`, `POST /commentaires/`~~ ✅ fait (`require_admin` + `UserPublic`, accès self/admin, auteur déduit du token) | Critique |
|  Court terme | ~~Corriger les 3 bugs bloquants (`/commentaires/all`, `/commentaires/chapitre/{id}`, `DELETE /commentaires/{id}`)~~ ✅ fait (voir §5.1) | Élevé |
| ⚡ Court terme | Unifier les identifiants (`ObjectId` vs `id` string) + index MongoDB | Élevé |
| ✅ Moyen terme | ~~Tests automatisés, `lifespan`, logging, pagination, suppression en cascade~~ ✅ fait (smoke_test + test_audio_flow, `lifespan` + logging, `skip`/`limit` sur livres/chapitres/commentaires, cascade livres→chapitres→commentaires/lectures + audio Cloudinary) | Moyen |
| ✅ Moyen terme | ~~Nettoyage Git (`env/`), allègement de `requirements.txt`, `lifespan` + `logging`~~ ✅ fait pour `.gitignore` (`env/`) + `lifespan` + `logging` (reste : allègement de `requirements.txt`) | Moyen |
| 🚀 Long terme | CI/CD, observabilité, TTS/STT, recherche, notifications, modération | Valeur produit |

---

## 8. Note de méthode

Ce document a été produit après une analyse **statique** (lecture de l'intégralité
des fichiers Python, de la configuration et de l'historique Git) et **dynamique**
du dépôt :

- état analysé : commit `b6e497b`, branche `main` ;
- vérification de syntaxe : `python -m py_compile` sur tous les modules → **OK** ;
- chargement de l'application : 32 routes déclarées, schéma OpenAPI généré → **OK** ;
- les points de la section 5 ont été confirmés par lecture du code, et les trois
  bugs bloquants ont été reproduits par exécution (validation Pydantic et
  sérialisation `model_dump()`).

> **Mise à jour — CRUD commentaires corrigé (§5.1).** Les six défauts
> identifiés sur les commentaires (points 1, 2, 3, 4, 8 et 14) ont été
> corrigés dans `app/models.py`, `app/routes/comment.py`,
> `app/services/commentaire_service.py` et
> `../voix-africaine-web/src/pages/ListeChapitres.jsx`. Le reste de
> l'analyse (sections 5 à 7) demeure une feuille de route.

Aucune autre correction de code n'a été appliquée : ce fichier reste un état
des lieux et une feuille de route pour les points non traités.

> **Mise à jour — sécurisation `GET /auth/{user_id}`, pagination,
> suppression en cascade, `lifespan` + logging, `.gitignore`.**
> - `GET /auth/{user_id}` : accès réservé à l'utilisateur lui-même ou à un
>   administrateur (`app/routes/auth.py`) ;
> - pagination `skip`/`limit` ajoutée sur `GET /livres/public/`,
>   `GET /chapitres/public` et `GET /chapitres/livre/{livre_id}`
>   (`app/routes/livres.py`, `app/routes/chapitres.py`,
>   `app/services/livre_service.py`, `app/services/chapitre_service.py`) ;
> - suppression en cascade : `DELETE /livres/{id}` efface les chapitres du
>   livre puis leurs commentaires/lectures ; `DELETE /chapitres/{id}` efface
>   l'audio Cloudinary puis les commentaires/lectures liés ;
> - `main.py` utilise le `lifespan` (plus de `@app.on_event("startup")`
>   déprécié) + `logging` de base ;
> - `.gitignore` couvre désormais `env/` et `.pytest_cache/`.
> Vérifié par `scripts/smoke_test.py` (23/23 OK) + contrôles manuels
> (`GET /auth/{id}` self→200 / tiers→403, cascade livre→chapitre→commentaires).

> **Mise à jour — passage en environnement local.** Depuis cette analyse :
> - Docker a été retiré du suivi Git (`Dockerfile`, `docker-compose.yml`) ;
> - MongoDB Atlas a été remplacé par un `mongod` local (`mongodb://localhost:27017`) ;
> - `app/bootstrap.py` crée les index et l'administrateur par défaut au démarrage ;
> - le `.env` est désormais prioritaire sur les variables d'environnement du shell ;
> - `scripts/init_db.py`, `scripts/smoke_test.py` et `scripts/run_dev.sh` ont été ajoutés ;
> - le frontend pointe sur `http://localhost:8000` et les URLs ont été alignées
>   sur les routes FastAPI (plus de redirections 307).
> Les points de la section 5 restent ouverts.
