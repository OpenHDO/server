"""FastAPI application for the OpenHDO Python server runtime."""

from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
import json
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError
from starlette.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from .config import ServerSettings, load_settings
from .connections import LightEventHub, LinkerConnections
from .logging import configure_logging, log_event
from .models import (
    BrightnessCommandEnvelope,
    CommandResultEnvelope,
    HealthResponse,
    LightCommandEnvelope,
    LightPatchRequest,
    LightStateReportedEnvelope,
    LightUpdatedEnvelope,
    Identifier,
    LinkRegisterEnvelope,
    LinkerEnvelope,
    LightsResponse,
    PowerCommandEnvelope,
    ProblemResponse,
    RgbColorCommandEnvelope,
    LightView,
    Source,
    utc_now,
)
from .repository import InMemoryLightRepository
from .service import LightService, ServiceError


_SOURCE_ADAPTER = TypeAdapter(Source)


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


def _origin_matches(headers, allowed_origins: tuple[str, ...]) -> bool:
    return not allowed_origins or headers.get("origin") in allowed_origins


def create_app(settings: ServerSettings | None = None) -> FastAPI:
    settings = settings or load_settings()
    logger = configure_logging(settings.log_level)
    repository = InMemoryLightRepository(clock=utc_now)
    connections = LinkerConnections()
    events = LightEventHub()
    service = LightService(
        repository=repository,
        transport=connections,
        events=events,
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
        yield
        log_event(logger, logging.INFO, "server.shutdown", {"instance_name": settings.instance_name})

    application = FastAPI(title="OpenHDO Server", version="0.1.0", lifespan=lifespan)
    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "PATCH", "POST"],
            allow_headers=["Authorization", "Content-Type", "Accept", "X-OpenHDO-Source"],
        )
    application.state.settings = settings
    application.state.service = service
    application.state.connections = connections
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

    async def require_authorization(request: Request) -> None:
        if not _token_matches(request.headers, settings.api_token):
            raise ServiceError(401, "authorization_required", "a valid bearer token is required")

    @application.middleware("http")
    async def protect_admin(request: Request, call_next):
        if settings.api_token and (
            request.url.path == "/admin" or request.url.path.startswith("/admin/")
        ) and not _token_matches(request.headers, settings.api_token):
            return JSONResponse(
                status_code=401,
                content=ProblemResponse(
                    error="authorization_required",
                    detail="a valid bearer token is required",
                ).model_dump(mode="json"),
            )
        return await call_next(request)

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
        dependencies=[Depends(require_authorization)],
    )
    async def submit_command(light_id: Identifier, command: LightCommandEnvelope) -> CommandResultEnvelope:
        if command.payload.light_id != light_id:
            raise ServiceError(409, "light_mismatch", "path light id does not match command payload")
        return await service.submit_command(command)

    @application.patch(
        "/api/v1/lights/{light_id}",
        response_model=CommandResultEnvelope,
        status_code=202,
        dependencies=[Depends(require_authorization)],
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

    @application.websocket("/api/v1/events")
    async def events_socket(websocket: WebSocket) -> None:
        if not _origin_matches(websocket.headers, settings.cors_origins):
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
            await connections.detach(linker_id, websocket)

    if application.state.admin_panel_available:
        application.mount("/admin", StaticFiles(directory=str(web_dist), html=True), name="server-admin")
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

    return application


def _validate_linker_message(raw_message: object) -> LinkerEnvelope:
    from pydantic import TypeAdapter

    return TypeAdapter(LinkerEnvelope).validate_python(raw_message)


app = create_app()
