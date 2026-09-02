"""FastAPI application for the OpenHDO Python server runtime."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
import hmac
import json
import logging
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import TypeAdapter, ValidationError
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from .config import ServerSettings, load_settings
from .connections import LightEventHub, LinkerConnections
from .auth import AuthConflict, AuthStore, UserRecord
from .logging import configure_logging, log_event
from .models import (
    AuthResponse,
    AuthUser,
    BrightnessCommandEnvelope,
    CommandResultEnvelope,
    DiscoveryCandidateEnvelope,
    DiscoveryCompletedEnvelope,
    DiscoverySessionResponse,
    DiscoveryStartRequest,
    HealthResponse,
    LightCommandEnvelope,
    LightPatchRequest,
    LightStateReportedEnvelope,
    LightUpdatedEnvelope,
    Identifier,
    LinkRegisterEnvelope,
    LinkerEnvelope,
    LightsResponse,
    LoginRequest,
    PowerCommandEnvelope,
    ProblemResponse,
    RegisterRequest,
    RgbColorCommandEnvelope,
    LightView,
    Source,
    UserUpdateRequest,
    UsersResponse,
    utc_now,
)
from .repository import InMemoryDiscoverySessionRepository, InMemoryLightRepository
from .service import DiscoveryService, LightService, ServiceError


_SOURCE_ADAPTER = TypeAdapter(Source)
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


def _token_matches(headers, expected: str | None) -> bool:
    if expected is None:
        return True
    provided = _authorization_value(headers)
    return provided is not None and hmac.compare_digest(provided, expected)


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
    repository = InMemoryLightRepository(clock=utc_now)
    discovery_repository = InMemoryDiscoverySessionRepository()
    connections = LinkerConnections()
    events = LightEventHub()
    auth_store = AuthStore(settings.auth_db_path)
    auth_store.ensure_bootstrap_admin(settings.admin_username, settings.admin_password)
    service = LightService(
        repository=repository,
        transport=connections,
        events=events,
        instance_name=settings.instance_name,
        logger=logger,
    )
    discovery_service = DiscoveryService(
        repository=discovery_repository,
        transport=connections,
        instance_name=settings.instance_name,
        logger=logger,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        log_event(
            logger,
            logging.INFO,
            "server.startup",
            {"runtime": "python", "instance_name": settings.instance_name, "host": settings.host, "port": settings.port},
        )
        try:
            yield
        finally:
            await discovery_service.close()
            auth_store.close()
            log_event(logger, logging.INFO, "server.shutdown", {"instance_name": settings.instance_name})

    application = FastAPI(title="OpenHDO Server", version="0.1.0", lifespan=lifespan)
    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "PATCH", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Accept", "X-OpenHDO-Source", "X-OpenHDO-CSRF"],
        )
    application.state.settings = settings
    application.state.service = service
    application.state.discovery_service = discovery_service
    application.state.connections = connections
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
                detail=json.dumps(error.errors(), default=str, separators=(",", ":")),
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

    @application.get("/api/v1/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            instance_name=settings.instance_name,
            linkers_connected=await connections.count(),
        )

    @application.get("/api/v1/lights", response_model=LightsResponse, dependencies=[Depends(require_authorization)])
    async def list_lights() -> LightsResponse:
        return LightsResponse(lights=service.list_lights())

    @application.get(
        "/api/v1/lights/{light_id}",
        response_model=LightView,
        dependencies=[Depends(require_authorization)],
    )
    async def get_light(light_id: Identifier) -> LightView:
        return service.get_light(light_id)

    @application.post(
        "/api/v1/lights/{light_id}/commands",
        response_model=CommandResultEnvelope,
        status_code=202,
        dependencies=[Depends(require_user), Depends(require_csrf)],
    )
    async def submit_command(light_id: Identifier, command: LightCommandEnvelope) -> CommandResultEnvelope:
        if command.payload.light_id != light_id:
            raise ServiceError(409, "light_mismatch", "path light id does not match command payload")
        return await service.submit_command(command)

    @application.patch(
        "/api/v1/lights/{light_id}",
        response_model=CommandResultEnvelope,
        status_code=202,
        dependencies=[Depends(require_user), Depends(require_csrf)],
    )
    async def patch_light(
        request: Request,
        light_id: Identifier,
        change: LightPatchRequest,
    ) -> CommandResultEnvelope:
        try:
            source = _SOURCE_ADAPTER.validate_python(request.headers.get("x-openhdo-source", "http.client"))
        except ValidationError as error:
            raise ServiceError(422, "validation_error", str(error)) from error
        command_id = uuid4()
        if change.power is not None:
            command: LightCommandEnvelope = PowerCommandEnvelope(
                v=1,
                id=command_id,
                type="light.command.power",
                ts=utc_now(),
                source=source,
                correlation_id=uuid4(),
                payload={
                    "light_id": light_id,
                    "command_id": command_id,
                    "idempotency_key": change.idempotency_key,
                    "power": change.power,
                },
            )
        elif change.brightness is not None:
            command = BrightnessCommandEnvelope(
                v=1,
                id=command_id,
                type="light.command.brightness",
                ts=utc_now(),
                source=source,
                correlation_id=uuid4(),
                payload={
                    "light_id": light_id,
                    "command_id": command_id,
                    "idempotency_key": change.idempotency_key,
                    "brightness": change.brightness,
                },
            )
        else:
            command = RgbColorCommandEnvelope(
                v=1,
                id=command_id,
                type="light.command.rgb_color",
                ts=utc_now(),
                source=source,
                correlation_id=uuid4(),
                payload={
                    "light_id": light_id,
                    "command_id": command_id,
                    "idempotency_key": change.idempotency_key,
                    "rgb_color": change.rgb_color,
                },
            )
        return await service.submit_command(command)

    @application.post(
        "/api/v1/discovery/sessions",
        response_model=DiscoverySessionResponse,
        status_code=202,
        dependencies=[Depends(require_user), Depends(require_csrf)],
    )
    async def start_discovery(request: DiscoveryStartRequest) -> DiscoverySessionResponse:
        return await discovery_service.start(request)

    @application.get(
        "/api/v1/discovery/sessions/{session_id}",
        response_model=DiscoverySessionResponse,
        dependencies=[Depends(require_authorization)],
    )
    async def get_discovery_session(session_id: UUID) -> DiscoverySessionResponse:
        return discovery_service.get(session_id)

    @application.websocket("/api/v1/events")
    async def events_socket(websocket: WebSocket) -> None:
        if not _origin_matches(websocket.headers, settings.cors_origins, require_origin=True):
            await websocket.close(code=4403, reason="origin not allowed")
            return
        if not _token_matches(websocket.headers, settings.api_token):
            await websocket.close(code=4401, reason="authorization required")
            return
        await websocket.accept()
        queue = events.subscribe()
        try:
            while True:
                event: LightUpdatedEnvelope = await queue.get()
                await websocket.send_json(event.model_dump(mode="json"))
        except WebSocketDisconnect:
            pass
        finally:
            events.unsubscribe(queue)

    @application.websocket("/api/v1/linkers/{linker_id}")
    async def linker_socket(websocket: WebSocket, linker_id: Identifier) -> None:
        if not _origin_matches(websocket.headers, settings.cors_origins):
            await websocket.close(code=4403, reason="origin not allowed")
            return
        if not _token_matches(websocket.headers, settings.api_token):
            await websocket.close(code=4401, reason="authorization required")
            return
        await connections.attach(linker_id, websocket)
        registered = False
        try:
            while True:
                raw_message = await websocket.receive_json()
                try:
                    message = _validate_linker_message(raw_message)
                except ValidationError as error:
                    await websocket.close(code=1003, reason=f"invalid v1 linker envelope: {error}")
                    return
                if message.source != linker_id:
                    await websocket.close(code=1008, reason="message source does not match linker path")
                    return
                try:
                    if isinstance(message, LinkRegisterEnvelope):
                        await service.register_linker(linker_id, message)
                        registered = True
                    elif not registered:
                        await websocket.close(code=1008, reason="link.register is required first")
                        return
                    elif isinstance(message, LightStateReportedEnvelope):
                        await service.ingest_state(linker_id, message)
                    elif isinstance(message, DiscoveryCandidateEnvelope):
                        await discovery_service.ingest_candidate(linker_id, message)
                    elif isinstance(message, DiscoveryCompletedEnvelope):
                        await discovery_service.ingest_completed(linker_id, message)
                    else:
                        await service.ingest_result(linker_id, message)
                except ServiceError as error:
                    log_event(
                        logger,
                        logging.WARNING,
                        "linker.message_rejected",
                        {"linker_id": linker_id, "error": error.code},
                    )
                    await websocket.close(code=1008, reason=error.detail)
                    return
        except WebSocketDisconnect:
            pass
        finally:
            was_current = await connections.detach(linker_id, websocket)
            if was_current:
                await discovery_service.linker_disconnected(linker_id)

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


def _validate_linker_message(raw_message: object) -> LinkerEnvelope:
    from pydantic import TypeAdapter

    return TypeAdapter(LinkerEnvelope).validate_python(raw_message)


def _auth_user(user: UserRecord) -> AuthUser:
    return AuthUser(
        id=user.id,
        username=user.username,
        role=user.role,
        active=user.active,
        created_at=user.created_at,
    )


app = create_app()
