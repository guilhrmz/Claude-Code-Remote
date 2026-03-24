"""
Handler para integração com Claude Code via Ollama.
"""

import asyncio
import subprocess
import shlex
import os
from typing import Optional, AsyncGenerator
from datetime import datetime
import httpx
from server.config import settings


class OllamaClient:
    """Cliente para comunicação com Ollama API."""

    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model
        self.timeout = settings.ollama_timeout
        self._client = httpx.AsyncClient(timeout=self.timeout)

    async def chat(self, message: str, system_prompt: Optional[str] = None) -> str:
        """
        Envia mensagem para o Ollama e retorna resposta.
        """
        endpoint = f"{self.base_url}/api/chat"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False
        }

        try:
            response = await self._client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")
        except httpx.HTTPError as e:
            raise RuntimeError(f"Ollama API error: {e}")
        except Exception as e:
            raise RuntimeError(f"Error communicating with Ollama: {e}")

    async def chat_stream(
        self, message: str, system_prompt: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream de resposta do Ollama.
        """
        endpoint = f"{self.base_url}/api/chat"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True
        }

        try:
            async with self._client.stream("POST", endpoint, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.strip():
                        import json
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
        except Exception as e:
            raise RuntimeError(f"Stream error: {e}")

    async def health_check(self) -> bool:
        """Verifica se Ollama está disponível."""
        try:
            response = await self._client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except:
            return False

    async def close(self):
        """Fecha cliente HTTP."""
        await self._client.aclose()


class ClaudeHandler:
    """
    Handler principal para processar requisições do Claude Code.
    Combina Ollama com execução de comandos e manipulação de arquivos.
    """

    def __init__(self, work_dir: str):
        self.ollama = OllamaClient()
        self.work_dir = work_dir
        self.sessions: dict[str, list[dict]] = {}  # session_id -> messages
        self._ensure_work_dir()

    def _ensure_work_dir(self):
        """Cria diretório de trabalho se não existir."""
        os.makedirs(self.work_dir, exist_ok=True)

    def _get_system_prompt(self) -> str:
        """Retorna prompt de sistema para o Claude."""
        return """Você é um assistente de programação e automação.
Você tem acesso a:
- Execução de comandos shell
- Leitura e escrita de arquivos
- Listagem de diretórios

Sempre que o usuário solicitar uma ação, execute-a diretamente.
Seja conciso e direto nas respostas."""

    async def process_chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None
    ) -> dict:
        """
        Processa mensagem de chat e retorna resposta.
        """
        if session_id is None:
            session_id = f"session_{datetime.utcnow().timestamp()}"

        if session_id not in self.sessions:
            self.sessions[session_id] = []

        # Adiciona mensagem ao histórico
        self.sessions[session_id].append({
            "role": "user",
            "content": message,
            "timestamp": datetime.utcnow().isoformat()
        })

        # Constrói contexto da conversa
        context = self._build_context(session_id)

        # Usa Ollama para gerar resposta
        prompt = system_prompt or self._get_system_prompt()

        try:
            response = await self.ollama.chat(
                message=context,
                system_prompt=prompt
            )

            # Adiciona resposta ao histórico
            self.sessions[session_id].append({
                "role": "assistant",
                "content": response,
                "timestamp": datetime.utcnow().isoformat()
            })

            return {
                "session_id": session_id,
                "content": response,
                "model": settings.ollama_model,
                "message_count": len(self.sessions[session_id])
            }
        except Exception as e:
            return {
                "session_id": session_id,
                "content": f"Error: {str(e)}",
                "error": True
            }

    def _build_context(self, session_id: str) -> str:
        """Constrói contexto da conversa."""
        messages = self.sessions.get(session_id, [])
        if not messages:
            return ""

        context_lines = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            context_lines.append(f"{role}: {content}")

        return "\n".join(context_lines)

    async def execute_command(
        self, command: str, cwd: Optional[str] = None, timeout: int = 60
    ) -> dict:
        """
        Executa comando shell e retorna output.
        """
        work_cwd = cwd or self.work_dir

        start_time = datetime.utcnow()

        try:
            # Parse comando de forma segura
            args = shlex.split(command)

            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_cwd
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return {
                    "stdout": "",
                    "stderr": f"Command timeout after {timeout}s",
                    "return_code": -1,
                    "error": True
                }

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            return {
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "return_code": proc.returncode or 0,
                "execution_time": execution_time
            }

        except FileNotFoundError:
            return {
                "stdout": "",
                "stderr": f"Command not found: {command}",
                "return_code": 127,
                "error": True
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": f"Execution error: {str(e)}",
                "return_code": -1,
                "error": True
            }

    async def read_file(self, file_path: str) -> dict:
        """
        Lê conteúdo de arquivo.
        """
        full_path = self._resolve_path(file_path)

        try:
            if not os.path.exists(full_path):
                return {
                    "file_path": file_path,
                    "content": "",
                    "exists": False
                }

            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            return {
                "file_path": file_path,
                "content": content,
                "exists": True,
                "size": len(content)
            }
        except Exception as e:
            return {
                "file_path": file_path,
                "content": "",
                "exists": False,
                "error": str(e)
            }

    async def write_file(
        self, file_path: str, content: str, mode: str = "w"
    ) -> dict:
        """
        Escreve conteúdo em arquivo.
        """
        full_path = self._resolve_path(file_path)

        # Cria diretórios intermediários
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        try:
            with open(full_path, mode, encoding="utf-8") as f:
                f.write(content)

            return {
                "file_path": file_path,
                "bytes_written": len(content),
                "success": True
            }
        except Exception as e:
            return {
                "file_path": file_path,
                "error": str(e),
                "success": False
            }

    async def list_directory(self, path: str, recursive: bool = False) -> dict:
        """
        Lista conteúdo de diretório.
        """
        full_path = self._resolve_path(path)

        if not os.path.exists(full_path):
            return {
                "path": path,
                "files": [],
                "directories": [],
                "error": "Path does not exist"
            }

        files = []
        directories = []

        if recursive:
            for root, dirs, filenames in os.walk(full_path):
                rel_root = os.path.relpath(root, full_path)
                for d in dirs:
                    dir_path = os.path.join(rel_root, d) if rel_root != "." else d
                    directories.append(dir_path)
                for f in filenames:
                    file_path = os.path.join(rel_root, f) if rel_root != "." else f
                    files.append(file_path)
        else:
            for item in os.listdir(full_path):
                item_path = os.path.join(full_path, item)
                if os.path.isdir(item_path):
                    directories.append(item)
                else:
                    files.append(item)

        return {
            "path": path,
            "files": files,
            "directories": directories
        }

    def _resolve_path(self, file_path: str) -> str:
        """
        Resolve caminho relativo ao diretório de trabalho.
        Previne path traversal.
        """
        # Remove .. para prevenir path traversal
        if ".." in file_path:
            raise ValueError("Path traversal not allowed")

        if os.path.isabs(file_path):
            return file_path

        return os.path.join(self.work_dir, file_path)

    async def cleanup_session(self, session_id: str):
        """Limpa sessão."""
        self.sessions.pop(session_id, None)

    async def health_check(self) -> dict:
        """Verifica saúde do handler."""
        ollama_ok = await self.ollama.health_check()
        return {
            "status": "healthy" if ollama_ok else "degraded",
            "ollama_available": ollama_ok,
            "work_dir": self.work_dir,
            "active_sessions": len(self.sessions)
        }

    async def close(self):
        """Fecha recursos."""
        await self.ollama.close()
