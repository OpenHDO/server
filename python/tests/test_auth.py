from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from openhdo_server.app import create_app
from openhdo_server.auth import AuthStore
from openhdo_server.config import ServerSettings


class AuthApiTests(unittest.TestCase):
    def test_legacy_roles_are_migrated_to_user(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "auth.sqlite3"
            connection = sqlite3.connect(database_path)
            connection.execute(
                """
                CREATE TABLE users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('admin', 'operator', 'viewer')),
                    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.executemany(
                "INSERT INTO users(id, username, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
                [
                    ("admin-id", "admin", "hash", "admin", "2026-01-01T00:00:00Z"),
                    ("viewer-id", "viewer", "hash", "viewer", "2026-01-01T00:00:00Z"),
                ],
            )
            connection.commit()
            connection.close()

            store = AuthStore(str(database_path))
            self.assertEqual({user.username: user.role for user in store.list_users()}, {"admin": "admin", "viewer": "user"})
            store.close()

    def test_registration_creates_user_account(self) -> None:
        with TemporaryDirectory() as directory:
            settings = ServerSettings(
                auth_db_path=str(Path(directory) / "auth.sqlite3"),
                admin_username="admin",
                admin_password="correct-password",
            )
            with TestClient(create_app(settings)) as client:
                registered = client.post(
                    "/api/v1/auth/register",
                    json={"username": "new-user", "password": "user-password"},
                )
                self.assertEqual(registered.status_code, 201)
                self.assertEqual(registered.json()["role"], "user")
                duplicate = client.post(
                    "/api/v1/auth/register",
                    json={"username": "new-user", "password": "user-password"},
                )
                self.assertEqual(duplicate.status_code, 409)

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
                registered = client.post(
                    "/api/v1/auth/register",
                    json={"username": "regular-user", "password": "user-password"},
                )
                self.assertEqual(registered.status_code, 201)
                user_id = registered.json()["id"]
                self.assertEqual(len(client.get("/api/v1/admin/users").json()["users"]), 2)
                self.assertEqual(
                    client.post(
                        "/api/v1/admin/users",
                        json={"username": "manual-user", "password": "user-password"},
                        headers={"X-OpenHDO-CSRF": csrf},
                    ).status_code,
                    405,
                )

                promoted = client.patch(
                    f"/api/v1/admin/users/{user_id}",
                    json={"role": "admin"},
                    headers={"X-OpenHDO-CSRF": csrf},
                )
                self.assertEqual(promoted.status_code, 200)
                self.assertEqual(promoted.json()["role"], "admin")
                demoted = client.patch(
                    f"/api/v1/admin/users/{user_id}",
                    json={"role": "user"},
                    headers={"X-OpenHDO-CSRF": csrf},
                )
                self.assertEqual(demoted.status_code, 200)
                self.assertEqual(demoted.json()["role"], "user")

                cannot_remove_last_admin = client.patch(
                    "/api/v1/admin/users/does-not-matter",
                    json={"role": "user"},
                    headers={"X-OpenHDO-CSRF": csrf},
                )
                self.assertEqual(cannot_remove_last_admin.status_code, 404)

                logout = client.post("/api/v1/auth/logout", headers={"X-OpenHDO-CSRF": csrf})
                self.assertEqual(logout.status_code, 204)
                self.assertEqual(client.get("/api/v1/auth/me").status_code, 401)

                user_login = client.post(
                    "/api/v1/auth/login",
                    json={"username": "regular-user", "password": "user-password"},
                )
                self.assertEqual(user_login.status_code, 200)
                self.assertEqual(client.get("/api/v1/lights").status_code, 200)
                self.assertEqual(client.get("/api/v1/admin/users").status_code, 403)

                user_csrf = client.cookies.get("openhdo_csrf")
                forbidden_update = client.patch(
                    f"/api/v1/admin/users/{user_id}",
                    json={"role": "admin"},
                    headers={"X-OpenHDO-CSRF": user_csrf},
                )
                self.assertEqual(forbidden_update.status_code, 403)

    def test_admin_can_delete_user_but_not_last_admin(self) -> None:
        with TemporaryDirectory() as directory:
            settings = ServerSettings(
                auth_db_path=str(Path(directory) / "auth.sqlite3"),
                admin_username="admin",
                admin_password="correct-password",
            )
            with TestClient(create_app(settings)) as client:
                registered = client.post(
                    "/api/v1/auth/register",
                    json={"username": "to-delete", "password": "user-password"},
                )
                user_id = registered.json()["id"]
                client.post(
                    "/api/v1/auth/login",
                    json={"username": "admin", "password": "correct-password"},
                )
                csrf = client.cookies.get("openhdo_csrf")
                deleted = client.delete(
                    f"/api/v1/admin/users/{user_id}",
                    headers={"X-OpenHDO-CSRF": csrf},
                )
                self.assertEqual(deleted.status_code, 204)
                self.assertEqual(client.get("/api/v1/admin/users").json()["users"][0]["username"], "admin")

                admin_id = client.get("/api/v1/admin/users").json()["users"][0]["id"]
                cannot_delete_last_admin = client.delete(
                    f"/api/v1/admin/users/{admin_id}",
                    headers={"X-OpenHDO-CSRF": csrf},
                )
                self.assertEqual(cannot_delete_last_admin.status_code, 409)

    def test_admin_can_register_linker(self) -> None:
        with TemporaryDirectory() as directory:
            data_dir = Path(directory) / "data"
            settings = ServerSettings(
                auth_db_path=str(Path(directory) / "auth.sqlite3"),
                data_dir=str(data_dir),
                admin_username="admin",
                admin_password="correct-password",
            )
            with TestClient(create_app(settings)) as client:
                client.post(
                    "/api/v1/auth/login",
                    json={"username": "admin", "password": "correct-password"},
                )
                csrf = client.cookies.get("openhdo_csrf")
                added = client.post(
                    "/api/v1/admin/linkers",
                    json={"id": "linker.office", "name": "Office Linker"},
                    headers={"X-OpenHDO-CSRF": csrf},
                )
                self.assertEqual(added.status_code, 201)
                self.assertFalse(added.json()["available"])
                self.assertEqual(client.get("/api/v1/linkers").json()["linkers"][0]["name"], "Office Linker")
                with client.websocket_connect("/api/v1/linkers/linker.office") as linker:
                    linker.send_json(
                        {
                            "v": 1,
                            "id": str(uuid4()),
                            "type": "link.register",
                            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                            "source": "linker.office",
                            "payload": {
                                "id": "linker.office",
                                "version": "1.0.0",
                                "name": "Office Linker",
                                "transports": ["local"],
                            },
                        }
                    )
                    live = client.get("/api/v1/linkers").json()["linkers"][0]
                    self.assertTrue(live["available"])
                    self.assertEqual(live["transports"], ["local"])
                duplicate = client.post(
                    "/api/v1/admin/linkers",
                    json={"id": "linker.office", "name": "Office Linker"},
                    headers={"X-OpenHDO-CSRF": csrf},
                )
                self.assertEqual(duplicate.status_code, 409)
            self.assertTrue((data_dir / "modules" / "connector" / "linkers.json").is_file())

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
