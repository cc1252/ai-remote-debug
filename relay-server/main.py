import asyncio
import os
import re
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

API_TOKEN = os.getenv("ARD_API_TOKEN", "")
COMMAND_TIMEOUT_SECONDS = 180
MAX_ARTIFACT_BYTES = int(os.getenv("ARD_MAX_ARTIFACT_BYTES", str(512 * 1024 * 1024)))
ARTIFACT_DIR = Path(os.getenv("ARD_ARTIFACT_DIR", "artifacts"))
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def validate_configuration() -> None:
    if len(API_TOKEN) < 32 or API_TOKEN == "replace-with-relay-token":
        raise RuntimeError(
            "ARD_API_TOKEN must be set to a random token of at least 32 characters"
        )
    if MAX_ARTIFACT_BYTES <= 0:
        raise RuntimeError("ARD_MAX_ARTIFACT_BYTES must be greater than zero")


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_configuration()
    yield


app = FastAPI(title="Android Remote Debug Relay", version="0.2.0", lifespan=lifespan)


class DeviceRegisterRequest(BaseModel):
    device_id: str | None = None
    name: str = "Android Device"
    android_version: str | None = None
    model: str | None = None
    root: bool = False


class DeviceInfo(BaseModel):
    device_id: str
    name: str
    android_version: str | None = None
    model: str | None = None
    root: bool = False
    online: bool = False
    last_seen: float


class CommandRequest(BaseModel):
    action: str
    args: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class CommandEnvelope(BaseModel):
    request_id: str
    action: str
    args: dict[str, Any]


class CommandResult(BaseModel):
    request_id: str
    status: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int | None = None
    error: str | None = None


@dataclass
class DeviceState:
    info: DeviceInfo
    websocket: WebSocket | None = None
    pending: dict[str, asyncio.Future] = field(default_factory=dict)
    command_history: dict[str, CommandResult | CommandEnvelope] = field(default_factory=dict)
    log_subscribers: set[asyncio.Queue[str]] = field(default_factory=set)


devices: dict[str, DeviceState] = {}


def token_is_valid(candidate: str | None) -> bool:
    return bool(candidate) and secrets.compare_digest(candidate, API_TOKEN)


def require_token(authorization: str | None = Header(default=None)) -> None:
    scheme, _, candidate = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token_is_valid(candidate):
        raise HTTPException(status_code=401, detail="invalid token")


def artifact_path(artifact_id: str) -> Path:
    if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", artifact_id) is None:
        raise HTTPException(status_code=400, detail="invalid artifact id")
    return ARTIFACT_DIR / artifact_id


async def save_artifact(request: Request, path: Path) -> int:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_ARTIFACT_BYTES:
                raise HTTPException(status_code=413, detail="artifact too large")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid content-length") from exc

    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.part")
    size = 0
    try:
        with temporary_path.open("wb") as file:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_ARTIFACT_BYTES:
                    raise HTTPException(status_code=413, detail="artifact too large")
                file.write(chunk)
        temporary_path.replace(path)
        return size
    finally:
        temporary_path.unlink(missing_ok=True)


def now() -> float:
    return time.time()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/artifacts", dependencies=[Depends(require_token)])
async def upload_artifact(request: Request) -> dict[str, Any]:
    artifact_id = uuid.uuid4().hex
    path = artifact_path(artifact_id)
    size = await save_artifact(request, path)
    return {"artifact_id": artifact_id, "size": size}


@app.post("/api/artifacts/{artifact_id}", dependencies=[Depends(require_token)])
async def upload_named_artifact(artifact_id: str, request: Request) -> dict[str, Any]:
    path = artifact_path(artifact_id)
    size = await save_artifact(request, path)
    return {"artifact_id": artifact_id, "size": size}


@app.get("/api/artifacts/{artifact_id}", dependencies=[Depends(require_token)])
def download_artifact(artifact_id: str) -> FileResponse:
    path = artifact_path(artifact_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(path, media_type="application/octet-stream", filename=artifact_id)


@app.get("/api/artifacts/{artifact_id}/meta", dependencies=[Depends(require_token)])
def artifact_meta(artifact_id: str) -> dict[str, Any]:
    path = artifact_path(artifact_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    return {"artifact_id": artifact_id, "size": path.stat().st_size}


@app.delete("/api/artifacts/{artifact_id}", dependencies=[Depends(require_token)])
def delete_artifact(artifact_id: str) -> dict[str, Any]:
    """Delete an artifact. Required hygiene for sensitive one-shot transfers
    (e.g. workspace DB snapshots used during remote login-state recovery)."""
    path = artifact_path(artifact_id)
    path.unlink(missing_ok=True)
    return {"deleted": artifact_id}


@app.post("/api/devices/register", dependencies=[Depends(require_token)])
def register_device(request: DeviceRegisterRequest) -> DeviceInfo:
    device_id = request.device_id or uuid.uuid4().hex
    info = DeviceInfo(
        device_id=device_id,
        name=request.name,
        android_version=request.android_version,
        model=request.model,
        root=request.root,
        online=device_id in devices and devices[device_id].websocket is not None,
        last_seen=now(),
    )
    state = devices.get(device_id)
    if state is None:
        devices[device_id] = DeviceState(info=info)
    else:
        state.info = info
    return devices[device_id].info


@app.get("/api/devices", response_model=list[DeviceInfo], dependencies=[Depends(require_token)])
def list_devices() -> list[DeviceInfo]:
    return [state.info for state in devices.values()]


@app.get("/api/devices/{device_id}", response_model=DeviceInfo, dependencies=[Depends(require_token)])
def get_device(device_id: str) -> DeviceInfo:
    state = devices.get(device_id)
    if state is None:
        raise HTTPException(status_code=404, detail="device not found")
    return state.info


@app.post("/api/devices/{device_id}/commands", response_model=CommandResult | CommandEnvelope, dependencies=[Depends(require_token)])
async def send_command(device_id: str, request: CommandRequest, wait: bool = True) -> CommandResult | CommandEnvelope:
    state = devices.get(device_id)
    if state is None:
        raise HTTPException(status_code=404, detail="device not found")
    if state.websocket is None:
        raise HTTPException(status_code=409, detail="device offline")

    request_id = request.request_id or uuid.uuid4().hex
    envelope = CommandEnvelope(request_id=request_id, action=request.action, args=request.args)
    state.command_history[request_id] = envelope

    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    state.pending[request_id] = future
    await state.websocket.send_json({
        "type": "command",
        "requestId": envelope.request_id,
        "action": envelope.action,
        "args": envelope.args,
    })

    if not wait:
        return envelope

    try:
        result = await asyncio.wait_for(future, timeout=COMMAND_TIMEOUT_SECONDS)
        return result
    except asyncio.TimeoutError:
        state.pending.pop(request_id, None)
        result = CommandResult(request_id=request_id, status="timeout", error="command timed out")
        state.command_history[request_id] = result
        return result


@app.get("/api/devices/{device_id}/commands/{request_id}", response_model=CommandResult | CommandEnvelope, dependencies=[Depends(require_token)])
def get_command(device_id: str, request_id: str) -> CommandResult | CommandEnvelope:
    state = devices.get(device_id)
    if state is None:
        raise HTTPException(status_code=404, detail="device not found")
    result = state.command_history.get(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail="command not found")
    return result


@app.get("/api/devices/{device_id}/logs/stream", dependencies=[Depends(require_token)])
async def stream_logs(device_id: str) -> StreamingResponse:
    state = devices.get(device_id)
    if state is None:
        raise HTTPException(status_code=404, detail="device not found")

    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=200)
    state.log_subscribers.add(queue)

    async def events():
        try:
            while True:
                line = await queue.get()
                yield f"data: {line}\n\n"
        finally:
            state.log_subscribers.discard(queue)

    return StreamingResponse(events(), media_type="text/event-stream")


@app.websocket("/ws/mobile/{device_id}")
async def mobile_socket(websocket: WebSocket, device_id: str, token: str | None = None) -> None:
    scheme, _, header_token = websocket.headers.get("authorization", "").partition(" ")
    candidate = header_token if scheme.lower() == "bearer" else token
    if not token_is_valid(candidate):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    state = devices.get(device_id)
    if state is None:
        state = DeviceState(
            info=DeviceInfo(device_id=device_id, name=device_id, online=True, last_seen=now())
        )
        devices[device_id] = state

    state.websocket = websocket
    state.info.online = True
    state.info.last_seen = now()

    try:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")
            state.info.last_seen = now()

            if message_type == "hello":
                state.info.name = message.get("name", state.info.name)
                state.info.android_version = message.get("androidVersion", state.info.android_version)
                state.info.model = message.get("model", state.info.model)
                state.info.root = bool(message.get("root", state.info.root))
                await websocket.send_json({"type": "hello_ack", "deviceId": device_id})
            elif message_type == "result":
                result = CommandResult(
                    request_id=message["requestId"],
                    status=message.get("status", "ok"),
                    exit_code=message.get("exitCode"),
                    stdout=message.get("stdout", ""),
                    stderr=message.get("stderr", ""),
                    duration_ms=message.get("durationMs"),
                    error=message.get("error"),
                )
                state.command_history[result.request_id] = result
                future = state.pending.pop(result.request_id, None)
                if future is not None and not future.done():
                    future.set_result(result)
            elif message_type == "log":
                line = str(message.get("line", ""))
                for subscriber in list(state.log_subscribers):
                    if not subscriber.full():
                        subscriber.put_nowait(line)
            elif message_type == "heartbeat":
                await websocket.send_json({"type": "heartbeat_ack", "ts": now()})
    except WebSocketDisconnect:
        pass
    finally:
        if state.websocket is websocket:
            state.websocket = None
            state.info.online = False
            state.info.last_seen = now()
            for request_id, future in state.pending.items():
                if not future.done():
                    future.set_result(CommandResult(request_id=request_id, status="offline", error="device disconnected"))
            state.pending.clear()
