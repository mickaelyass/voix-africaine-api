"""
Test de fumée de bout en bout de l'API Voix Africaine.

Vérifie que l'API répond, que l'admin par défaut peut s'authentifier et
que le cycle complet livres → chapitres → commentaires fonctionne, puis
nettoie les données de test qu'il a créées.

L'API doit déjà tourner.

Usage, depuis la racine du projet :

    env/bin/python -m scripts.smoke_test
    API_URL=http://127.0.0.1:9000 env/bin/python -m scripts.smoke_test

Code de sortie 0 si tout passe, 1 sinon.
"""

import os
import sys
import uuid

import httpx

BASE = os.environ.get("API_URL", "http://127.0.0.1:8000")
ADMIN_EMAIL = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@voixafricaine.com")
ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "Admin@Voix2026")

results: list[tuple[str, bool, str]] = []
known_issues: list[tuple[str, bool, str]] = []


def check(label: str, ok: bool, detail: str = "", known: bool = False) -> bool:
    """Enregistre une vérification.

    `known=True` signale un défaut déjà identifié dans l'analyse
    (cf. readme.md section 5) : il est reporté sans faire échouer la suite.
    """

    suffix = f" — {detail}" if detail else ""

    if known and not ok:
        known_issues.append((label, ok, detail))
        print(f"⚠️  {label}{suffix} (échec connu, à corriger)")
        return False

    results.append((label, ok, detail))
    print(f"{'✅' if ok else '❌'} {label}{suffix}")
    return ok


def report() -> int:
    failed = [r for r in results if not r[1]]

    print()
    if known_issues:
        print(f"⚠️  {len(known_issues)} échec(s) connu(s) — non bloquant(s) :")
        for label, _, detail in known_issues:
            print(f"   - {label} {detail}")
        print()

    print("=" * 62)
    if failed:
        print(f"❌ {len(failed)}/{len(results)} vérifications en échec")
        for label, _, detail in failed:
            print(f"   - {label} {detail}")
        return 1

    print(f"✅ {len(results)}/{len(results)} vérifications réussies")
    return 0


def main() -> int:

    with httpx.Client(base_url=BASE, timeout=20) as client:

        # ==========================================
        # 1. Endpoints publics
        # ==========================================

        r = client.get("/docs")
        check("GET /docs (Swagger)", r.status_code == 200, f"HTTP {r.status_code}")

        r = client.get("/livres/public/")
        check("GET /livres/public/", r.status_code == 200, f"HTTP {r.status_code}")

        # ==========================================
        # 2. Authentification de l'admin par défaut
        # ==========================================

        r = client.post(
            "/auth/token",
            data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        if not check(
            "POST /auth/token (admin par défaut)",
            r.status_code == 200,
            f"HTTP {r.status_code}",
        ):
            return report()

        auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = client.get("/auth/me", headers=auth)
        check("GET /auth/me", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code != 200:
            return report()

        admin = r.json()
        check(
            "  → rôle administrateur",
            admin.get("role") == "admin",
            str(admin.get("role", "")),
        )

        return suite_crud(client, auth, admin)


def suite_crud(client, auth, admin) -> int:
    """Cycle livre → chapitre → commentaire, avec nettoyage."""

    livre_id = str(uuid.uuid4())
    chapitre_id = str(uuid.uuid4())
    comment_id = None

    try:
        # ==========================================
        # 3. Livres
        # ==========================================

        r = client.post(
            "/livres/",
            headers=auth,
            json={
                "id": livre_id,
                "titre": f"__smoke_livre_{livre_id[:8]}",
                "auteur": "Smoke Test",
                "description": "Créé puis supprimé par scripts/smoke_test.py",
                "is_public": True,
            },
        )
        check("POST /livres/ (admin)", r.status_code == 200, f"HTTP {r.status_code}")

        r = client.get(f"/livres/{livre_id}", headers=auth)
        check("GET /livres/{id}", r.status_code == 200, f"HTTP {r.status_code}")

        # ==========================================
        # 4. Chapitres
        # ==========================================

        r = client.post(
            "/chapitres/",
            headers=auth,
            json={
                "id": chapitre_id,
                "livre_id": livre_id,
                "titre": "__smoke_chapitre",
                "numero": 1,
                "contenu_texte": "Contenu de test.",
                "is_public": True,
            },
        )
        check("POST /chapitres/ (admin)", r.status_code == 200, f"HTTP {r.status_code}")

        r = client.get(f"/chapitres/livre/{livre_id}", headers=auth)
        check("GET /chapitres/livre/{id}", r.status_code == 200, f"HTTP {r.status_code}")

        r = client.patch(f"/chapitres/{chapitre_id}/toggle-public", headers=auth)
        check(
            "PATCH /chapitres/{id}/toggle-public",
            r.status_code == 200,
            f"HTTP {r.status_code}",
        )

        r = client.get("/chapitres/public")
        check("GET /chapitres/public", r.status_code == 200, f"HTTP {r.status_code}")

        # ==========================================
        # 5. Commentaires
        # ==========================================

        r = client.post(
            "/commentaires/",
            headers=auth,
            json={
                "contenu": "Commentaire de smoke test",
                "timestamp": 1.5,
                "chapitre_id": chapitre_id,
            },
        )
        check("POST /commentaires/", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            comment_id = r.json().get("id")
            check(
                "  → auteur déduit du token",
                (r.json().get("user_info") or {}).get("id") == admin["id"],
                str((r.json().get("user_info") or {}).get("id")),
            )

        # --- l'user_id du corps ne doit pas permettre l'usurpation ---
        r = client.post(
            "/commentaires/",
            headers=auth,
            json={
                "contenu": "Tentative d'usurpation",
                "timestamp": 2.0,
                "chapitre_id": chapitre_id,
                "user_id": "000000000000000000000000",
            },
        )
        check(
            "POST /commentaires/ (user_id du corps ignoré)",
            r.status_code == 200
            and (r.json().get("user_info") or {}).get("id") == admin["id"],
            f"HTTP {r.status_code}",
        )
        if r.status_code == 200:
            spoof_id = r.json().get("id")
            if spoof_id:
                client.delete(f"/commentaires/{spoof_id}", headers=auth)

        r = client.get(
            "/commentaires/",
            headers=auth,
            params={"chapitre_id": chapitre_id},
        )
        check(
            "GET /commentaires/?chapitre_id=",
            r.status_code == 200 and len(r.json()) >= 1,
            f"HTTP {r.status_code}",
        )

        r = client.get(
            "/commentaires/",
            headers=auth,
            params={"chapitre_id": chapitre_id, "limit": 1},
        )
        check(
            "GET /commentaires/?limit=1 (pagination)",
            r.status_code == 200 and len(r.json()) == 1,
            f"HTTP {r.status_code} — {len(r.json()) if r.status_code == 200 else '?'} élément(s)",
        )

        r = client.get("/commentaires/all", headers=auth)
        check(
            "GET /commentaires/all",
            r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) >= 1,
            f"HTTP {r.status_code}",
        )

        r = client.get(f"/commentaires/chapitre/{chapitre_id}", headers=auth)
        check(
            "GET /commentaires/chapitre/{id}",
            r.status_code == 200 and len(r.json().get("commentaires") or []) >= 1,
            f"HTTP {r.status_code}",
        )

        if comment_id:
            r = client.delete(f"/commentaires/{comment_id}", headers=auth)
            check(
                "DELETE /commentaires/{id}",
                r.status_code == 204,
                f"HTTP {r.status_code}",
            )

            r = client.delete(f"/commentaires/{comment_id}", headers=auth)
            check(
                "DELETE /commentaires/{id} (déjà supprimé)",
                r.status_code == 404,
                f"HTTP {r.status_code}",
            )

    finally:
        # ==========================================
        # 6. Nettoyage
        # ==========================================

        r = client.delete(f"/chapitres/{chapitre_id}", headers=auth)
        check(
            "DELETE /chapitres/{id} (nettoyage)",
            r.status_code in (200, 204, 404),
            f"HTTP {r.status_code}",
        )

        r = client.delete(f"/livres/{livre_id}", headers=auth)
        check(
            "DELETE /livres/{id} (nettoyage)",
            r.status_code in (200, 204, 404),
            f"HTTP {r.status_code}",
        )

    # ==========================================
    # 7. CORS pour le frontend local
    # ==========================================

    r = client.options(
        "/auth/token",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    check(
        "Preflight CORS depuis http://localhost:3000",
        r.headers.get("access-control-allow-origin") == "http://localhost:3000",
        r.headers.get("access-control-allow-origin", "en-tête absent"),
    )

    return report()


if __name__ == "__main__":
    sys.exit(main())