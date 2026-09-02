from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from openhdo_server.app import create_app
from openhdo_server.config import ServerSettings


class AuthApiTests(unittest.TestCase):
    def test_login_sessions_csrf_and_role_management(self) -> None:
        with TemporaryDirectory() as directory:
            settings = ServerSettings(
                auth_db_path=str(Path(directory) / "auth.sqlite3"),
                admin_username="admin",
                admin_password="correct-password",
            )
            with TestClient(create_app(settings)) as client:
                self.assertEqual(client.get("/api/v1/auth/me").status_code, 401)
                self.assertEqual(
                    client.post(
                        "/api/v1/auth/login",
                        json={"username": "admin", "password": "wrong-password"},
                    ).status_code,
                    401,
                )

                login = client.post(
                    "/api/v1/auth/login",
                    json={"username": "admin", "password": "correct-password"},
                )
                self.assertEqual(login.status_code, 200)
                self.assertEqual(login.json()["user"]["role"], "admin")
                self.assertIn("openhdo_session", client.cookies)
                self.assertIn("openhdo_csrf", client.cookies)
                self.assertEqual(client.get("/api/v1/auth/me").json()["user"]["username"], "admin")

                csrf = client.cookies.get("openhdo_csrf")
                missing_csrf = client.post(
                    "/api/v1/admin/users",
                    json={"username": "operator", "password": "operator-password", "role": "operator"},
                )
                self.assertEqual(missing_csrf.status_code, 403)

                created = client.post(
                    "/api/v1/admin/users",
                    json={"username": "operator", "password": "operator-password", "role": "operator"},
                    headers={"X-OpenHDO-CSRF": csrf},
                )
                self.assertEqual(created.status_code, 201)
                operator_id = created.json()["id"]
                self.assertEqual(len(client.get("/api/v1/admin/users").json()["users"]), 2)

                cannot_remove_last_admin = client.patch(
                    "/api/v1/admin/users/does-not-matter",
                    json={"role": "viewer"},
                    headers={"X-OpenHDO-CSRF": csrf},
                )
                self.assertEqual(cannot_remove_last_admin.status_code, 404)

                logout = client.post("/api/v1/auth/logout", headers={"X-OpenHDO-CSRF": csrf})
                self.assertEqual(logout.status_code, 204)
                self.assertEqual(client.get("/api/v1/auth/me").status_code, 401)

                operator_login = client.post(
                    "/api/v1/auth/login",
                    json={"username": "operator", "password": "operator-password"},
                )
                self.assertEqual(operator_login.status_code, 200)
                self.assertEqual(client.get("/api/v1/lights").status_code, 200)
                self.assertEqual(client.get("/api/v1/admin/users").status_code, 403)

                operator_csrf = client.cookies.get("openhdo_csrf")
                demoted = client.patch(
                    f"/api/v1/admin/users/{operator_id}",
                    json={"role": "viewer"},
                    headers={"X-OpenHDO-CSRF": operator_csrf},
                )
                self.assertEqual(demoted.status_code, 403)

    def test_last_active_admin_cannot_be_removed(self) -> None:
        with TemporaryDirectory() as directory:
            settings = ServerSettings(
                auth_db_path=str(Path(directory) / "auth.sqlite3"),
                admin_username="admin",
                admin_password="correct-password",
            )
            with TestClient(create_app(settings)) as client:
                client.post(
                    "/api/v1/auth/login",
                    json={"username": "admin", "password": "correct-password"},
                )
                csrf = client.cookies.get("openhdo_csrf")
                admin_id = client.get("/api/v1/admin/users").json()["users"][0]["id"]
                response = client.patch(
                    f"/api/v1/admin/users/{admin_id}",
                    json={"active": False},
                    headers={"X-OpenHDO-CSRF": csrf},
                )
                self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
