"""
Cliente WebSocket para comunicação com o servidor remoto.
Implementa reconexão automática, keep-alive e tratamento de erros.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Callable, Any
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from client.config import settings
from shared.protocol import (
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
    SessionEndMessage,
    parse_message,
)
from shared.models import SessionState


logger = logging.getLogger(__name__)


class RemoteClient:
    """
    Cliente principal para comunicação remota.
    Gerencia conexão WebSocket, autenticação e envio/recebimento de mensagens.
    """

    def __init__(
        self,
        server_url: Optional[str] = None,
        client_id: Optional[str] = None,
        secret_key: Optional[str] = None
    ):
        self.server_url = server_url or settings.server_url
        self.client_id = client_id or settings.client_id
        self.secret_key = secret_key or settings.secret_key

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False
        self._authenticated = False
        self._access_token: Optional[str] = None
        self._session_id: Optional[str] = None
        self._reconnect_attempts = 0
        self._running = False

        # Callbacks
        self._on_message: Optional[Callable[[dict], Any]] = None
        self._on_connect: Optional[Callable[[], Any]] = None
        self._on_disconnect: Optional[Callable[[], Any]] = None
        self._on_error: Optional[Callable[[Exception], Any]] = None

        # Task para receiver
        self._receiver_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

        # Queue para mensagens pendentes
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._responses: dict[str, asyncio.Future] = {}

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    async def connect(self) -> bool:
        """
        Estabelece conexão com o servidor.
        Implementa reconexão automática com backoff exponencial.
        """
        self._running = True

        while self._running:
            try:
                logger.info(f"Connecting to {self.server_url}...")

                async with websockets.connect(
                    self.server_url,
                    ping_interval=settings.ping_interval,
                    ping_timeout=settings.ping_timeout,
                    max_size=10 * 1024 * 1024,  # 10MB
                ) as websocket:
                    self._ws = websocket
                    self._connected = True
                    self._reconnect_attempts = 0

                    logger.info("Connected to server")

                    # Notifica callback
                    if self._on_connect:
                        await self._on_connect()

                    # Autentica
                    await self._authenticate()

                    if self._authenticated:
                        # Inicia tasks
                        self._receiver_task = asyncio.create_task(self._receive_loop())
                        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                        # Aguarda até desconectar
                        await self._wait_for_disconnect()

                    self._connected = False

            except ConnectionClosed as e:
                logger.warning(f"Connection closed: {e.code} - {e.reason}")
                self._connected = False
                await self._cleanup()

            except WebSocketException as e:
                logger.error(f"WebSocket error: {e}")
                self._connected = False
                await self._cleanup()

            except Exception as e:
                logger.error(f"Connection error: {e}")
                if self._on_error:
                    await self._on_error(e)

            # Reconexão
            if self._running:
                await self._attempt_reconnect()

        return False

    async def _authenticate(self):
        """Autentica no servidor."""
        try:
            auth_msg = AuthRequest(
                client_id=self.client_id,
                secret_key=self.secret_key
            )

            # Envia e aguarda resposta
            response = await self._send_and_wait(auth_msg.model_dump())

            if response.get("type") == MessageType.AUTH_RESPONSE:
                auth_resp = AuthResponse(**response)
                if auth_resp.status == "success":
                    self._authenticated = True
                    self._access_token = auth_resp.access_token
                    logger.info("Authentication successful")
                else:
                    logger.error(f"Authentication failed: {auth_resp.message}")
                    self._authenticated = False
            else:
                logger.error("Unexpected auth response")
                self._authenticated = False

        except Exception as e:
            logger.error(f"Auth error: {e}")
            self._authenticated = False

    async def _receive_loop(self):
        """Loop de recebimento de mensagens."""
        try:
            while self._connected and self._running:
                try:
                    data = await self._ws.recv()
                    message = json.loads(data)

                    logger.debug(f"Received: {message.get('type')}")

                    # Notifica callback
                    if self._on_message:
                        await self._on_message(message)

                    # Resolve future se existir
                    msg_id = message.get("id")
                    if msg_id and msg_id in self._responses:
                        future = self._responses.pop(msg_id)
                        future.set_result(message)

                except asyncio.CancelledError:
                    break
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON received: {e}")

        except asyncio.CancelledError:
            pass

    async def _heartbeat_loop(self):
        """Envia keep-alive periódico."""
        try:
            while self._connected and self._running:
                await asyncio.sleep(settings.ping_interval)

                if self._connected:
                    try:
                        keepalive = KeepAliveMessage(type=MessageType.SESSION_KEEPALIVE)
                        await self._send(keepalive.model_dump())
                    except Exception:
                        logger.warning("Heartbeat failed")

        except asyncio.CancelledError:
            pass

    async def _wait_for_disconnect(self):
        """Aguarda desconexão."""
        while self._connected and self._running:
            await asyncio.sleep(0.1)

    async def _attempt_reconnect(self):
        """Tenta reconectar com backoff."""
        if self._reconnect_attempts >= settings.reconnect_attempts:
            logger.error("Max reconnect attempts reached")
            self._running = False
            return

        delay = min(
            settings.reconnect_delay * (settings.reconnect_backoff ** self._reconnect_attempts),
            60  # Max 60s
        )

        self._reconnect_attempts += 1
        logger.info(f"Reconnecting in {delay:.1f}s (attempt {self._reconnect_attempts})")
        await asyncio.sleep(delay)

    async def _cleanup(self):
        """Limpa recursos."""
        if self._receiver_task:
            self._receiver_task.cancel()
            try:
                await self._receiver_task
            except asyncio.CancelledError:
                pass
            self._receiver_task = None

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        self._ws = None

    async def disconnect(self):
        """Desconecta do servidor."""
        self._running = False

        # Envia session end se autenticado
        if self._authenticated:
            try:
                end_msg = SessionEndMessage(type=MessageType.SESSION_END)
                await self._send(end_msg.model_dump())
            except Exception:
                pass

        await self._cleanup()

        if self._on_disconnect:
            await self._on_disconnect()

        logger.info("Disconnected")

    async def _send(self, data: dict) -> bool:
        """Envia mensagem."""
        if not self._ws or not self._connected:
            return False

        try:
            await self._ws.send(json.dumps(data))
            return True
        except Exception as e:
            logger.error(f"Send error: {e}")
            return False

    async def _send_and_wait(self, data: dict, timeout: int = 30) -> dict:
        """Envia mensagem e aguarda resposta."""
        msg_id = data.get("id")
        future = asyncio.Future()
        self._responses[msg_id] = future

        if not await self._send(data):
            raise RuntimeError("Not connected")

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._responses.pop(msg_id, None)
            raise

    # Métodos públicos de API

    async def send_chat(
        self,
        content: str,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None
    ) -> ChatResponse:
        """
        Envia mensagem de chat para o Claude.
        """
        msg = ChatMessage(
            content=content,
            session_id=session_id or self._session_id,
            system_prompt=system_prompt
        )

        response = await self._send_and_wait(msg.model_dump())
        chat_resp = ChatResponse(**response)

        if chat_resp.status == "success":
            self._session_id = chat_resp.session_id

        return chat_resp

    async def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 60
    ) -> CommandOutput:
        """
        Executa comando shell no servidor.
        """
        msg = CommandMessage(
            command=command,
            cwd=cwd,
            timeout=timeout
        )

        response = await self._send_and_wait(msg.model_dump())
        return CommandOutput(**response)

    async def read_file(self, file_path: str) -> FileContent:
        """
        Lê arquivo no servidor.
        """
        msg = FileReadRequest(file_path=file_path)
        response = await self._send_and_wait(msg.model_dump())
        return FileContent(**response)

    async def write_file(
        self,
        file_path: str,
        content: str,
        mode: str = "w"
    ) -> FileCreated:
        """
        Escreve arquivo no servidor.
        """
        msg = FileWriteRequest(
            file_path=file_path,
            content=content,
            mode=mode
        )

        response = await self._send_and_wait(msg.model_dump())

        if response.get("type") == MessageType.FILE_CREATED:
            return FileCreated(**response)
        else:
            raise RuntimeError(f"File write failed: {response}")

    async def list_directory(
        self,
        path: str,
        recursive: bool = False
    ) -> DirectoryListing:
        """
        Lista diretório no servidor.
        """
        msg = DirectoryListRequest(
            path=path,
            recursive=recursive
        )

        response = await self._send_and_wait(msg.model_dump())
        return DirectoryListing(**response)

    async def get_status(self) -> StatusMessage:
        """Obtém status do servidor."""
        msg = StatusMessage(type=MessageType.STATUS)
        response = await self._send_and_wait(msg.model_dump())
        return StatusMessage(**response)

    # Callbacks

    def on_message(self, callback: Callable[[dict], Any]):
        """Set callback para mensagens recebidas."""
        self._on_message = callback

    def on_connect(self, callback: Callable[[], Any]):
        """Set callback para conexão."""
        self._on_connect = callback

    def on_disconnect(self, callback: Callable[[], Any]):
        """Set callback para desconexão."""
        self._on_disconnect = callback

    def on_error(self, callback: Callable[[Exception], Any]):
        """Set callback para erros."""
        self._on_error = callback


async def main():
    """Exemplo de uso do cliente."""
    client = RemoteClient()

    async def on_message(msg: dict):
        print(f"[RECV] {msg.get('type')}: {msg}")

    async def on_connect():
        print("[INFO] Connected")

    async def on_disconnect():
        print("[INFO] Disconnected")

    async def on_error(e: Exception):
        print(f"[ERROR] {e}")

    client.on_message(on_message)
    client.on_connect(on_connect)
    client.on_disconnect(on_disconnect)
    client.on_error(on_error)

    try:
        # Conecta em background
        connect_task = asyncio.create_task(client.connect())

        # Dá tempo para conectar
        await asyncio.sleep(2)

        if client.is_authenticated:
            # Testa chat
            print("[INFO] Sending chat message...")
            response = await client.send_chat("Hello, Claude!")
            print(f"[RESPONSE] {response.content}")

            # Testa comando
            print("[INFO] Running command...")
            cmd_resp = await client.run_command("ls -la")
            print(f"[STDOUT] {cmd_resp.stdout}")

        # Aguarda
        await asyncio.sleep(5)

    except KeyboardInterrupt:
        pass
    finally:
        await client.disconnect()
        connect_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
