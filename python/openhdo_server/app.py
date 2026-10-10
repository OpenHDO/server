"""FastAPI application for the OpenHDO Python server runtime."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import hmac
import json
import logging
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from .config import ServerSettings, load_settings
from .auth import AuthConflict, AuthStore, UserRecord
from .logging import configure_logging, log_event
from .models import AuthResponse, AuthUser, LoginRequest, ProblemResponse, RegisterRequest, UserUpdateRequest, UsersResponse, utc_now
from .plugins import PluginManager, plugin_router
from .service import ServiceError
from .integrations import IntegrationManager, integration_router
from .lights import lights_router, light_view


_SESSION_COOKIE = "openhdo_session"
_CSRF_COOKIE = "openhdo_csrf"
_SESSION_TTL_SECONDS = 8 * 60 * 60


class AdminStaticFiles(StaticFiles):
    """Serve the panel entry for unknown client-side routes, not missing assets."""

    def __init__(self, *args, index_path: Path, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._index_path = index_path

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code == 404 and "." not in Path(path).name:
                return FileResponse(self._index_path)
            raise


@dataclass(frozen=True)
class Principal:
    kind: Literal["user", "token", "legacy"]
    role: str
    user: UserRecord | None = None


def _authorization_value(headers) -> str | None:
    value = headers.get("authorization")
    if value is None or not value.startswith("Bearer "):
        return None
    return value[7:]


def _api_token_matches(headers, expected: str | None) -> bool:
    if expected is None:
        return False
    provided = _authorization_value(headers)
    return provided is not None and hmac.compare_digest(provided, expected)


def _origin_matches(
    headers, allowed_origins: tuple[str, ...], *, require_origin: bool = False
) -> bool:
    origin = headers.get("origin")
    return not allowed_origins or origin in allowed_origins or (origin is None and not require_origin)


def create_app(settings: ServerSettings | None = None) -> FastAPI:
    settings = settings or load_settings()
    logger = configure_logging(settings.log_level)
    integrations = IntegrationManager(Path(settings.data_dir) / "devices" / "integrations.sqlite3")
    plugins = PluginManager(settings.data_dir, {"devices": integrations, "http": integrations.client})
    integrations.plugin_providers = plugins.providers
    integrations.plugin_events = plugins.emit
    auth_store = AuthStore(settings.auth_db_path)
    auth_store.ensure_bootstrap_admin(settings.admin_username, settings.admin_password)
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        log_event(
            logger,
            logging.INFO,
            "server.startup",
            {"runtime": "python", "instance_name": settings.instance_name, "host": settings.host, "port": settings.port},
        )
        await plugins.start()
        connector_task = asyncio.create_task(integrations.run())
        try:
            yield
        finally:
            connector_task.cancel()
            await asyncio.gather(connector_task, return_exceptions=True)
            await plugins.close()
            await integrations.close()
            auth_store.close()
            log_event(logger, logging.INFO, "server.shutdown", {"instance_name": settings.instance_name})

    application = FastAPI(title="OpenHDO Server", version="0.1.0", lifespan=lifespan)
    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "PATCH", "POST", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Accept", "X-OpenHDO-Source", "X-OpenHDO-CSRF"],
        )
    application.state.settings = settings
    application.state.plugins = plugins
    application.state.integrations = integrations
    application.state.auth_store = auth_store
    web_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    admin_index = web_dist / "index.html"
    application.state.admin_panel_available = admin_index.is_file()

    @application.exception_handler(ServiceError)
    async def handle_service_error(_: Request, error: ServiceError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content=ProblemResponse(error=error.code, detail=error.detail).model_dump(mode="json"),
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=ProblemResponse(
                error="validation_error",
                detail=json.dumps([{key: item[key] for key in ("type", "loc", "msg") if key in item} for item in error.errors()], default=str, separators=(",", ":")),
            ).model_dump(mode="json"),
        )

    def principal_for(request: Request) -> Principal | None:
        if _api_token_matches(request.headers, settings.api_token):
            return Principal(kind="token", role="admin")
        user = auth_store.session(request.cookies.get(_SESSION_COOKIE))
        if user is not None:
            return Principal(kind="user", role=user.role, user=user)
        if settings.api_token is None and not auth_store.has_users():
            return Principal(kind="legacy", role="admin")
        return None

    async def require_authorization(request: Request) -> Principal:
        principal = principal_for(request)
        if principal is None:
            raise ServiceError(401, "authorization_required", "a valid bearer token is required")
        return principal

    async def require_user(request: Request) -> Principal:
        principal = await require_authorization(request)
        if principal.role not in {"admin", "user"}:
            raise ServiceError(403, "forbidden", "user role is required")
        return principal

    async def require_admin(request: Request) -> Principal:
        principal = await require_authorization(request)
        if principal.kind == "legacy" or principal.role != "admin":
            raise ServiceError(403, "forbidden", "admin role is required")
        return principal

    async def require_csrf(request: Request) -> Principal:
        principal = await require_authorization(request)
        if principal.kind == "user" and request.method not in {"GET", "HEAD", "OPTIONS"}:
            if not auth_store.csrf_matches(
                request.cookies.get(_SESSION_COOKIE), request.headers.get("x-openhdo-csrf")
            ):
                raise ServiceError(403, "csrf_required", "a valid CSRF token is required")
        return principal

    def session_user(request: Request) -> UserRecord:
        user = auth_store.session(request.cookies.get(_SESSION_COOKIE))
        if user is None:
            raise ServiceError(401, "authorization_required", "a valid admin session is required")
        return user

    @application.post("/api/v1/auth/login", response_model=AuthResponse)
    async def login(request: Request, credentials: LoginRequest, response: Response) -> AuthResponse:
        user = auth_store.authenticate(credentials.username, credentials.password)
        if user is None:
            raise ServiceError(401, "invalid_credentials", "username or password is invalid")
        session_token, csrf_token = auth_store.create_session(user, ttl_seconds=_SESSION_TTL_SECONDS)
        secure = request.url.scheme == "https"
        response.set_cookie(
            _SESSION_COOKIE,
            session_token,
            max_age=_SESSION_TTL_SECONDS,
            httponly=True,
            secure=secure,
            samesite="strict",
            path="/",
        )
        response.set_cookie(
            _CSRF_COOKIE,
            csrf_token,
            max_age=_SESSION_TTL_SECONDS,
            httponly=False,
            secure=secure,
            samesite="strict",
            path="/",
        )
        return AuthResponse(user=_auth_user(user))

    @application.post("/api/v1/auth/register", response_model=AuthUser, status_code=201)
    async def register(credentials: RegisterRequest) -> AuthUser:
        try:
            user = auth_store.register_user(credentials.username, credentials.password)
        except AuthConflict as error:
            raise ServiceError(409, "auth_conflict", str(error)) from error
        return _auth_user(user)

    @application.get("/api/v1/auth/me", response_model=AuthResponse)
    async def auth_me(request: Request) -> AuthResponse:
        return AuthResponse(user=_auth_user(session_user(request)))

    @application.post("/api/v1/auth/logout", status_code=204, dependencies=[Depends(require_csrf)])
    async def logout(request: Request, response: Response) -> Response:
        auth_store.revoke_session(request.cookies.get(_SESSION_COOKIE))
        response.delete_cookie(_SESSION_COOKIE, path="/")
        response.delete_cookie(_CSRF_COOKIE, path="/")
        response.status_code = 204
        return response

    @application.get(
        "/api/v1/admin/users",
        response_model=UsersResponse,
        dependencies=[Depends(require_admin)],
    )
    async def list_users() -> UsersResponse:
        return UsersResponse(users=[_auth_user(user) for user in auth_store.list_users()])

    @application.patch(
        "/api/v1/admin/users/{user_id}",
        response_model=AuthUser,
        dependencies=[Depends(require_admin), Depends(require_csrf)],
    )
    async def update_user(user_id: str, change: UserUpdateRequest) -> AuthUser:
        try:
            updated = auth_store.update_user(
                user_id,
                role=change.role,
                active=change.active,
                password=change.password,
            )
        except AuthConflict as error:
            status_code = 409 if "last active admin" in str(error) else 404
            raise ServiceError(status_code, "auth_conflict", str(error)) from error
        return _auth_user(updated)

    @application.delete(
        "/api/v1/admin/users/{user_id}",
        status_code=204,
        dependencies=[Depends(require_admin), Depends(require_csrf)],
    )
    async def delete_user(user_id: str) -> Response:
        try:
            auth_store.delete_user(user_id)
        except AuthConflict as error:
            status_code = 409 if "last active admin" in str(error) else 404
            raise ServiceError(status_code, "auth_conflict", str(error)) from error
        return Response(status_code=204)

    application.include_router(integration_router(integrations, require_authorization, require_admin, require_user, require_csrf))
    application.include_router(plugin_router(plugins, require_user, require_admin, require_csrf))

    application.include_router(lights_router(integrations, require_authorization, require_user, require_csrf, settings.instance_name))

    @application.get("/api/v1/health")
    async def health():
        return {"api_version": 1, "service": "openhdo-server", "runtime": "python", "status": "ok", "instance_name": settings.instance_name, "integrations_connected": sum(item["status"] == "connected" for item in integrations.integrations())}

    @application.websocket("/api/v1/events")
    async def events_socket(websocket: WebSocket):
        if not _origin_matches(websocket.headers, settings.cors_origins, require_origin=True):
            await websocket.close(code=4403, reason="origin not allowed")
            return
        if principal_for(websocket) is None:
            await websocket.close(code=4401, reason="authorization required")
            return
        await websocket.accept()
        previous = {}
        previous_devices = None
        next_heartbeat = asyncio.get_running_loop().time() + 20
        disconnected = asyncio.create_task(websocket.receive())
        try:
            while True:
                if principal_for(websocket) is None:
                    await websocket.close(code=4401, reason="session expired")
                    return
                current = {view["light_id"]: view for device in integrations.devices() if (view := light_view(device)) is not None}
                for light_id, view in current.items():
                    if previous.get(light_id) != view:
                        await websocket.send_json({"v": 1, "id": str(uuid4()), "type": "light.updated", "ts": utc_now().isoformat(), "source": settings.instance_name, "payload": view})
                previous = current
                if websocket.query_params.get('devices') == '1':
                    payload = {'devices': integrations.devices(), 'integrations': integrations.integrations(), 'rooms': integrations.rooms()}
                    # Poll timestamps are not composition changes.
                    comparison = {**payload, 'integrations': [{key: value for key, value in entry.items() if key != 'synced_at'} for entry in payload['integrations']]}
                    if comparison != previous_devices:
                        await websocket.send_json({'v': 1, 'id': str(uuid4()), 'type': 'devices.updated', 'ts': utc_now().isoformat(), 'source': settings.instance_name, 'payload': payload})
                        previous_devices = comparison
                    if asyncio.get_running_loop().time() >= next_heartbeat:
                        await websocket.send_json({'v': 1, 'id': str(uuid4()), 'type': 'devices.heartbeat', 'ts': utc_now().isoformat(), 'source': settings.instance_name, 'payload': {}})
                        next_heartbeat = asyncio.get_running_loop().time() + 20
                done, _ = await asyncio.wait({disconnected}, timeout=1)
                if done:
                    if disconnected.result()["type"] == "websocket.disconnect":
                        return
                    disconnected = asyncio.create_task(websocket.receive())
        except WebSocketDisconnect:
            pass
        finally:
            disconnected.cancel()
            await asyncio.gather(disconnected, return_exceptions=True)

    if application.state.admin_panel_available:
        @application.api_route("/", methods=["GET"], include_in_schema=False)
        async def home_panel(_: Request) -> FileResponse:
            return FileResponse(admin_index)

        application.mount(
            "/admin",
            AdminStaticFiles(directory=str(web_dist), html=True, index_path=admin_index),
            name="server-admin",
        )

        @application.api_route("/auth", methods=["GET"], include_in_schema=False)
        @application.api_route("/auth/", methods=["GET"], include_in_schema=False)
        async def auth_panel(_: Request) -> FileResponse:
            return FileResponse(admin_index)

        @application.api_route("/auth/{path:path}", methods=["GET"], include_in_schema=False)
        async def auth_panel_route(_: Request, path: str) -> FileResponse:
            del path
            return FileResponse(admin_index)
    else:
        @application.api_route("/admin", methods=["GET"], include_in_schema=False)
        @application.api_route("/admin/{path:path}", methods=["GET"], include_in_schema=False)
        async def admin_unavailable(_: Request, path: str = "") -> JSONResponse:
            del path
            return JSONResponse(
                status_code=404,
                content=ProblemResponse(
                    error="admin_panel_unavailable",
                    detail="build server/web to enable the server admin panel",
                ).model_dump(mode="json"),
            )

        @application.api_route("/auth", methods=["GET"], include_in_schema=False)
        @application.api_route("/auth/", methods=["GET"], include_in_schema=False)
        async def auth_unavailable(_: Request) -> JSONResponse:
            return JSONResponse(
                status_code=404,
                content=ProblemResponse(
                    error="auth_panel_unavailable",
                    detail="build server/web to enable the shared auth panel",
                ).model_dump(mode="json"),
            )

    return application


def _auth_user(user: UserRecord) -> AuthUser:
    return AuthUser(
        id=user.id,
        username=user.username,
        role=user.role,
        active=user.active,
        created_at=user.created_at,
    )


app = create_app()
