"""
Protocolo de comunicação entre cliente e servidor.
Define os tipos de mensagens e estrutura do protocolo.
"""

from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field
import uuid
from datetime import datetime


class MessageType(str, Enum):
    """Tipos de mensagens suportados."""
    # Cliente -> Servidor
    AUTH_REQUEST = "auth_request"
    COMMAND = "command"           # Executar comando shell
    CHAT_MESSAGE = "chat_message" # Enviar mensagem para o Claude
    FILE_READ = "file_read"       # Ler arquivo
    FILE_WRITE = "file_write"     # Escrever arquivo
    FILE_LIST = "file_list"       # Listar diretório
    SESSION_KEEPALIVE = "keepalive"
    SESSION_END = "session_end"

    # Servidor -> Cliente
    AUTH_RESPONSE = "auth_response"
    COMMAND_OUTPUT = "command_output"
    CHAT_RESPONSE = "chat_response"
    FILE_CONTENT = "file_content"
    FILE_CREATED = "file_created"
    DIRECTORY_LISTING = "directory_listing"
    ERROR = "error"
    STATUS = "status"
    KEEPALIVE_ACK = "keepalive_ack"


class MessageStatus(str, Enum):
    """Status da mensagem."""
    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"
    PROCESSING = "processing"


class BaseMessage(BaseModel):
    """Base para todas as mensagens."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: MessageType
    status: MessageStatus = MessageStatus.PENDING
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


class AuthRequest(BaseMessage):
    """Requisição de autenticação."""
    type: MessageType = MessageType.AUTH_REQUEST
    client_id: str
    secret_key: str


class AuthResponse(BaseMessage):
    """Resposta de autenticação."""
    type: MessageType = MessageType.AUTH_RESPONSE
    status: MessageStatus
    access_token: Optional[str] = None
    expires_in: int = 3600  # segundos
    message: str


class ChatMessage(BaseMessage):
    """Mensagem de chat para o Claude."""
    type: MessageType = MessageType.CHAT_MESSAGE
    content: str
    session_id: Optional[str] = None
    system_prompt: Optional[str] = None


class ChatResponse(BaseMessage):
    """Resposta do chat."""
    type: MessageType = MessageType.CHAT_RESPONSE
    content: str
    session_id: str
    model: str = "ollama"
    usage: Optional[dict] = None


class CommandMessage(BaseMessage):
    """Comando shell para executar."""
    type: MessageType = MessageType.COMMAND
    command: str
    cwd: Optional[str] = None
    timeout: int = 60


class CommandOutput(BaseMessage):
    """Output de comando executado."""
    type: MessageType = MessageType.COMMAND_OUTPUT
    stdout: str
    stderr: str
    return_code: int
    execution_time: float


class FileReadRequest(BaseMessage):
    """Requisição para ler arquivo."""
    type: MessageType = MessageType.FILE_READ
    file_path: str


class FileContent(BaseMessage):
    """Conteúdo de arquivo."""
    type: MessageType = MessageType.FILE_CONTENT
    file_path: str
    content: str
    exists: bool


class FileWriteRequest(BaseMessage):
    """Requisição para escrever arquivo."""
    type: MessageType = MessageType.FILE_WRITE
    file_path: str
    content: str
    mode: str = "w"


class FileCreated(BaseMessage):
    """Arquivo criado/modificado."""
    type: MessageType = MessageType.FILE_CREATED
    file_path: str
    bytes_written: int


class DirectoryListRequest(BaseMessage):
    """Requisição para listar diretório."""
    type: MessageType = MessageType.FILE_LIST
    path: str
    recursive: bool = False


class DirectoryListing(BaseMessage):
    """Listagem de diretório."""
    type: MessageType = MessageType.DIRECTORY_LISTING
    path: str
    files: list[str]
    directories: list[str]


class ErrorMessage(BaseMessage):
    """Mensagem de erro."""
    type: MessageType = MessageType.ERROR
    status: MessageStatus = MessageStatus.ERROR
    error_code: str
    message: str
    details: Optional[dict] = None


class StatusMessage(BaseMessage):
    """Mensagem de status."""
    type: MessageType = MessageType.STATUS
    status: MessageStatus = MessageStatus.SUCCESS
    server_status: str = "online"
    active_sessions: int = 0
    message: str = ""


class KeepAliveMessage(BaseMessage):
    """Keep-alive para manter conexão."""
    type: MessageType = MessageType.SESSION_KEEPALIVE


class KeepAliveAck(BaseMessage):
    """Ack de keep-alive."""
    type: MessageType = MessageType.KEEPALIVE_ACK
    status: MessageStatus = MessageStatus.SUCCESS


class SessionEndMessage(BaseMessage):
    """Finalizar sessão."""
    type: MessageType = MessageType.SESSION_END
    reason: str = "user_requested"


# Mapeamento de tipos para classes
MESSAGE_TYPES: dict[str, type[BaseMessage]] = {
    MessageType.AUTH_REQUEST: AuthRequest,
    MessageType.AUTH_RESPONSE: AuthResponse,
    MessageType.CHAT_MESSAGE: ChatMessage,
    MessageType.CHAT_RESPONSE: ChatResponse,
    MessageType.COMMAND: CommandMessage,
    MessageType.COMMAND_OUTPUT: CommandOutput,
    MessageType.FILE_READ: FileReadRequest,
    MessageType.FILE_CONTENT: FileContent,
    MessageType.FILE_WRITE: FileWriteRequest,
    MessageType.FILE_CREATED: FileCreated,
    MessageType.FILE_LIST: DirectoryListRequest,
    MessageType.DIRECTORY_LISTING: DirectoryListing,
    MessageType.ERROR: ErrorMessage,
    MessageType.STATUS: StatusMessage,
    MessageType.SESSION_KEEPALIVE: KeepAliveMessage,
    MessageType.KEEPALIVE_ACK: KeepAliveAck,
    MessageType.SESSION_END: SessionEndMessage,
}


def parse_message(data: dict) -> BaseMessage:
    """Parse de mensagem JSON para objeto."""
    msg_type = data.get("type")
    if msg_type in MESSAGE_TYPES:
        return MESSAGE_TYPES[msg_type](**data)
    raise ValueError(f"Unknown message type: {msg_type}")
