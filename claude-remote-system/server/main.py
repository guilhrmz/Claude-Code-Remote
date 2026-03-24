"""
Servidor WebSocket principal para comunicação remota com Claude Code.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Set, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from server.config import settings
from server.auth import auth_manager
from server.claude_handler import ClaudeHandler
from shared.protocol import (
    parse_message,
    MessageType,
    AuthRequest,
    AuthResponse,
    ChatMessage,
    ChatResponse,
    CommandMessage,
    CommandOutput,
    FileReadRequest,
    FileContent,
    FileWriteRequest,
    FileCreated,
    DirectoryListRequest,
    DirectoryListing,
    ErrorMessage,
    StatusMessage,
    KeepAliveMessage,
    KeepAliveAck,
    SessionEndMessage,
    BaseMessage,
)
from shared.models import SessionState, ClientInfo


# Configuração de logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Estado global do servidor
class ServerState:
    """Estado compartilhado do servidor."""

    def __init__(self):
        self.claude_handler: Optional[ClaudeHandler] = None
        self.active_connections: Dict[str, WebSocket] = {}
        self.authenticated_clients: Dict[str, ClientInfo] = {}
        self.client_sessions: Dict[str, str] = {}  # client_id -> session_id

    async def initialize(self):
        """Inicializa o handler do Claude."""
        self.claude_handler = ClaudeHandler(settings.work_dir)
        logger.info(f"Claude handler initialized with work_dir: {settings.work_dir}")

    async def shutdown(self):
        """Limpa recursos."""
        if self.claude_handler:
            await self.claude_handler.close()
        for ws in self.active_connections.values():
            await ws.close()
        self.active_connections.clear()
        self.authenticated_clients.clear()


server_state = ServerState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida da aplicação."""
    await server_state.initialize()
    yield
    await server_state.shutdown()


app = FastAPI(
    title="Claude Remote Server",
    description="Servidor WebSocket para comunicação remota com Claude Code",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    """Gerenciador de conexões WebSocket."""

    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}
        self.client_info: Dict[str, ClientInfo] = {}

    async def connect(self, websocket: WebSocket, client_id: str) -> bool:
        """Aceita conexão WebSocket."""
        try:
            await websocket.accept()
            self.connections[client_id] = websocket
            self.client_info[client_id] = ClientInfo(
                client_id=client_id,
                connected_at=datetime.utcnow(),
                last_activity=datetime.utcnow(),
                state=SessionState.CONNECTED,
                ip_address=websocket.client.host if websocket.client else None
            )
            logger.info(f"Client {client_id} connected")
            return True
        except Exception as e:
            logger.error(f"Failed to connect client {client_id}: {e}")
            return False

    def disconnect(self, client_id: str):
        """Remove conexão."""
        self.connections.pop(client_id, None)
        self.client_info.pop(client_id, None)
        logger.info(f"Client {client_id} disconnected")

    def is_connected(self, client_id: str) -> bool:
        """Verifica se cliente está conectado."""
        return client_id in self.connections

    def is_authenticated(self, client_id: str) -> bool:
        """Verifica se cliente está autenticado."""
        info = self.client_info.get(client_id)
        return info and info.state == SessionState.AUTHENTICATED

    def update_activity(self, client_id: str):
        """Atualiza última atividade."""
        if client_id in self.client_info:
            self.client_info[client_id].last_activity = datetime.utcnow()

    def update_state(self, client_id: str, state: SessionState):
        """Atualiza estado da sessão."""
        if client_id in self.client_info:
            self.client_info[client_id].state = state

    async def send(self, client_id: str, data: dict) -> bool:
        """Envia mensagem para cliente."""
        if client_id not in self.connections:
            return False
        try:
            ws = self.connections[client_id]
            await ws.send_json(data)
            return True
        except Exception as e:
            logger.error(f"Error sending to {client_id}: {e}")
            return False

    async def broadcast(self, data: dict, authenticated_only: bool = False):
        """Envia mensagem para todos os clientes."""
        for client_id in list(self.connections.keys()):
            if authenticated_only and not self.is_authenticated(client_id):
                continue
            await self.send(client_id, data)


manager = ConnectionManager()


async def handle_auth(websocket: WebSocket, message: dict) -> dict:
    """Handle de autenticação."""
    try:
        auth_req = AuthRequest(**message)
        client_id = auth_req.client_id
        secret_key = auth_req.secret_key

        # Verifica credenciais
        if not auth_manager.verify_client(client_id, secret_key):
            return AuthResponse(
                status="error",
                message="Invalid credentials"
            ).model_dump()

        # Gera token
        token = auth_manager.generate_token(client_id)

        # Atualiza estado
        manager.update_state(client_id, SessionState.AUTHENTICATED)

        logger.info(f"Client {client_id} authenticated")

        return AuthResponse(
            status="success",
            access_token=token,
            expires_in=settings.token_expire_hours * 3600,
            message="Authentication successful"
        ).model_dump()

    except Exception as e:
        logger.error(f"Auth error: {e}")
        return ErrorMessage(
            error_code="AUTH_ERROR",
            message=str(e)
        ).model_dump()


async def handle_chat(websocket: WebSocket, client_id: str, message: dict) -> dict:
    """Handle de mensagem de chat."""
    try:
        chat_msg = ChatMessage(**message)

        if not server_state.claude_handler:
            return ErrorMessage(
                error_code="HANDLER_NOT_READY",
                message="Claude handler not initialized"
            ).model_dump()

        # Processa mensagem
        result = await server_state.claude_handler.process_chat(
            message=chat_msg.content,
            session_id=chat_msg.session_id,
            system_prompt=chat_msg.system_prompt
        )

        # Salva session_id
        server_state.client_sessions[client_id] = result["session_id"]

        return ChatResponse(
            status="success",
            content=result["content"],
            session_id=result["session_id"],
            model=result.get("model", settings.ollama_model)
        ).model_dump()

    except Exception as e:
        logger.error(f"Chat error: {e}")
        return ErrorMessage(
            error_code="CHAT_ERROR",
            message=str(e)
        ).model_dump()


async def handle_command(websocket: WebSocket, message: dict) -> dict:
    """Handle de comando shell."""
    try:
        cmd_msg = CommandMessage(**message)

        if not server_state.claude_handler:
            return ErrorMessage(
                error_code="HANDLER_NOT_READY",
                message="Claude handler not initialized"
            ).model_dump()

        # Executa comando
        result = await server_state.claude_handler.execute_command(
            command=cmd_msg.command,
            cwd=cmd_msg.cwd,
            timeout=cmd_msg.timeout
        )

        return CommandOutput(
            status="success" if result.get("return_code", 0) == 0 else "error",
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
            return_code=result.get("return_code", 0),
            execution_time=result.get("execution_time", 0)
        ).model_dump()

    except Exception as e:
        logger.error(f"Command error: {e}")
        return ErrorMessage(
            error_code="COMMAND_ERROR",
            message=str(e)
        ).model_dump()


async def handle_file_read(websocket: WebSocket, message: dict) -> dict:
    """Handle de leitura de arquivo."""
    try:
        file_req = FileReadRequest(**message)

        if not server_state.claude_handler:
            return ErrorMessage(
                error_code="HANDLER_NOT_READY",
                message="Claude handler not initialized"
            ).model_dump()

        result = await server_state.claude_handler.read_file(file_req.file_path)

        return FileContent(
            status="success" if result.get("exists", False) else "error",
            file_path=result["file_path"],
            content=result.get("content", ""),
            exists=result.get("exists", False)
        ).model_dump()

    except Exception as e:
        logger.error(f"File read error: {e}")
        return ErrorMessage(
            error_code="FILE_READ_ERROR",
            message=str(e)
        ).model_dump()


async def handle_file_write(websocket: WebSocket, message: dict) -> dict:
    """Handle de escrita de arquivo."""
    try:
        file_req = FileWriteRequest(**message)

        if not server_state.claude_handler:
            return ErrorMessage(
                error_code="HANDLER_NOT_READY",
                message="Claude handler not initialized"
            ).model_dump()

        result = await server_state.claude_handler.write_file(
            file_path=file_req.file_path,
            content=file_req.content,
            mode=file_req.mode
        )

        if result.get("success"):
            return FileCreated(
                status="success",
                file_path=file_req.file_path,
                bytes_written=result.get("bytes_written", 0)
            ).model_dump()
        else:
            return ErrorMessage(
                error_code="FILE_WRITE_ERROR",
                message=result.get("error", "Unknown error")
            ).model_dump()

    except Exception as e:
        logger.error(f"File write error: {e}")
        return ErrorMessage(
            error_code="FILE_WRITE_ERROR",
            message=str(e)
        ).model_dump()


async def handle_dir_list(websocket: WebSocket, message: dict) -> dict:
    """Handle de listagem de diretório."""
    try:
        dir_req = DirectoryListRequest(**message)

        if not server_state.claude_handler:
            return ErrorMessage(
                error_code="HANDLER_NOT_READY",
                message="Claude handler not initialized"
            ).model_dump()

        result = await server_state.claude_handler.list_directory(
            path=dir_req.path,
            recursive=dir_req.recursive
        )

        return DirectoryListing(
            status="success",
            path=result["path"],
            files=result.get("files", []),
            directories=result.get("directories", [])
        ).model_dump()

    except Exception as e:
        logger.error(f"Directory list error: {e}")
        return ErrorMessage(
            error_code="DIR_LIST_ERROR",
            message=str(e)
        ).model_dump()


async def handle_keepalive(websocket: WebSocket, client_id: str) -> dict:
    """Handle de keep-alive."""
    manager.update_activity(client_id)
    return KeepAliveAck(status="success").model_dump()


async def handle_message(websocket: WebSocket, client_id: str, message: dict):
    """
    Router principal de mensagens.
    """
    msg_type = message.get("type")

    # Log de atividade
    manager.update_activity(client_id)

    # Rotear para handler apropriado
    if msg_type == MessageType.AUTH_REQUEST:
        response = await handle_auth(websocket, message)
    elif msg_type == MessageType.CHAT_MESSAGE:
        if not manager.is_authenticated(client_id):
            response = ErrorMessage(
                error_code="NOT_AUTHENTICATED",
                message="Please authenticate first"
            ).model_dump()
        else:
            response = await handle_chat(websocket, client_id, message)
    elif msg_type == MessageType.COMMAND:
        if not manager.is_authenticated(client_id):
            response = ErrorMessage(
                error_code="NOT_AUTHENTICATED",
                message="Please authenticate first"
            ).model_dump()
        else:
            response = await handle_command(websocket, message)
    elif msg_type == MessageType.FILE_READ:
        if not manager.is_authenticated(client_id):
            response = ErrorMessage(
                error_code="NOT_AUTHENTICATED",
                message="Please authenticate first"
            ).model_dump()
        else:
            response = await handle_file_read(websocket, message)
    elif msg_type == MessageType.FILE_WRITE:
        if not manager.is_authenticated(client_id):
            response = ErrorMessage(
                error_code="NOT_AUTHENTICATED",
                message="Please authenticate first"
            ).model_dump()
        else:
            response = await handle_file_write(websocket, message)
    elif msg_type == MessageType.FILE_LIST:
        if not manager.is_authenticated(client_id):
            response = ErrorMessage(
                error_code="NOT_AUTHENTICATED",
                message="Please authenticate first"
            ).model_dump()
        else:
            response = await handle_dir_list(websocket, message)
    elif msg_type == MessageType.SESSION_KEEPALIVE:
        response = await handle_keepalive(websocket, client_id)
    elif msg_type == MessageType.SESSION_END:
        # Finalizar sessão
        session_id = server_state.client_sessions.get(client_id)
        if session_id and server_state.claude_handler:
            await server_state.claude_handler.cleanup_session(session_id)
        manager.update_state(client_id, SessionState.DISCONNECTED)
        response = StatusMessage(
            status="success",
            message="Session ended"
        ).model_dump()
    else:
        response = ErrorMessage(
            error_code="UNKNOWN_MESSAGE_TYPE",
            message=f"Unknown message type: {msg_type}"
        ).model_dump()

    # Envia resposta
    await manager.send(client_id, response)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Endpoint WebSocket principal.
    """
    # Client ID inicial (pode ser sobrescrito após auth)
    client_id = "anonymous"

    if not await manager.connect(websocket, client_id):
        await websocket.close(code=1008, reason="Connection failed")
        return

    try:
        while True:
            try:
                # Recebe mensagem
                data = await websocket.receive_json()

                # Atualiza client_id se vier da mensagem
                if data.get("client_id"):
                    old_id = client_id
                    client_id = data["client_id"]
                    if old_id != client_id and old_id in manager.connections:
                        manager.disconnect(old_id)
                        manager.connections[client_id] = websocket
                        manager.client_info[client_id] = manager.client_info.pop(
                            manager.client_info.get(old_id, ClientInfo(
                                client_id=old_id,
                                connected_at=datetime.utcnow(),
                                last_activity=datetime.utcnow(),
                                state=SessionState.CONNECTED
                            ))
                        )

                # Processa mensagem
                await handle_message(websocket, client_id, data)

            except WebSocketDisconnect:
                logger.info(f"Client {client_id} disconnected")
                break
            except json.JSONDecodeError as e:
                # Mensagem JSON inválida
                error_resp = ErrorMessage(
                    error_code="INVALID_JSON",
                    message=f"Invalid JSON: {str(e)}"
                ).model_dump()
                await manager.send(client_id, error_resp)
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                error_resp = ErrorMessage(
                    error_code="INTERNAL_ERROR",
                    message=str(e)
                ).model_dump()
                await manager.send(client_id, error_resp)

    finally:
        manager.disconnect(client_id)


@app.get("/health")
async def health_check():
    """Endpoint de saúde."""
    if server_state.claude_handler:
        handler_status = await server_state.claude_handler.health_check()
    else:
        handler_status = {"status": "not_initialized"}

    return {
        "status": "healthy",
        "connections": len(manager.connections),
        "authenticated_clients": len(
            [c for c in manager.client_info.values()
             if c.state == SessionState.AUTHENTICATED]
        ),
        "handler": handler_status
    }


@app.get("/status")
async def status():
    """Endpoint de status."""
    return StatusMessage(
        server_status="online",
        active_sessions=len(manager.connections),
        message="Server running"
    ).model_dump()


def main():
    """Inicia o servidor."""
    uvicorn.run(
        "server.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False
    )


if __name__ == "__main__":
    main()
