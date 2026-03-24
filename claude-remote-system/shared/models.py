"""
Modelos de dados compartilhados entre cliente e servidor.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class SessionState(str, Enum):
    """Estado da sessão."""
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    ACTIVE = "active"
    DISCONNECTED = "disconnected"
    EXPIRED = "expired"


class ClientInfo(BaseModel):
    """Informações do cliente."""
    client_id: str
    connected_at: datetime
    last_activity: datetime
    state: SessionState = SessionState.CONNECTED
    ip_address: Optional[str] = None


class ServerConfig(BaseModel):
    """Configuração do servidor."""
    host: str = "0.0.0.0"
    port: int = 8765
    ssl_enabled: bool = False
    ssl_cert_path: Optional[str] = None
    ssl_key_path: Optional[str] = None
    auth_enabled: bool = True
    max_connections: int = 10
    session_timeout: int = 3600  # segundos
    heartbeat_interval: int = 30  # segundos


class ClientConfig(BaseModel):
    """Configuração do cliente."""
    server_url: str = "ws://localhost:8765"
    client_id: str = ""
    secret_key: str = ""
    reconnect_attempts: int = 3
    reconnect_delay: int = 5  # segundos
    heartbeat_interval: int = 30  # segundos


class OllamaConfig(BaseModel):
    """Configuração do Ollama."""
    base_url: str = "http://localhost:11434"
    model: str = "claude-code"
    timeout: int = 120
    stream: bool = False


class APISession(BaseModel):
    """Sessão de API ativa."""
    session_id: str
    client_id: str
    created_at: datetime
    last_message_at: datetime
    message_count: int = 0
