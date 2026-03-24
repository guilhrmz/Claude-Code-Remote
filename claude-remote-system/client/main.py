"""
Cliente CLI para comunicação com o servidor Claude Remote.
Permite envio de comandos, chat e operações de arquivo.
"""

import asyncio
import sys
import logging
from typing import Optional
import json

from client.ws_client import RemoteClient
from client.config import settings
from shared.protocol import MessageType


# Configuração de logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class InteractiveClient:
    """
    Cliente interativo com menu de comandos.
    """

    def __init__(self, server_url: str, client_id: str, secret_key: str):
        self.client = RemoteClient(
            server_url=server_url,
            client_id=client_id,
            secret_key=secret_key
        )
        self._running = True

    async def run(self):
        """Executa cliente interativo."""
        print("=" * 60)
        print("Claude Remote Client")
        print("=" * 60)
        print(f"Server: {self.client.server_url}")
        print(f"Client ID: {self.client.client_id}")
        print("-" * 60)

        # Configura callbacks
        self.client.on_connect(self._on_connect)
        self.client.on_disconnect(self._on_disconnect)
        self.client.on_error(self._on_error)

        # Conecta em background
        connect_task = asyncio.create_task(self.client.connect())

        # Aguarda conexão
        await asyncio.sleep(2)

        if not self.client.is_connected:
            print("[ERROR] Failed to connect")
            connect_task.cancel()
            return

        if not self.client.is_authenticated:
            print("[ERROR] Authentication failed")
            await self.client.disconnect()
            connect_task.cancel()
            return

        print("\n[SUCCESS] Connected and authenticated!")
        print("\nCommands:")
        print("  chat <message>     - Send chat message")
        print("  cmd <command>      - Run shell command")
        print("  cat <file>         - Read file")
        print("  echo <file> <text> - Write file")
        print("  ls [path]          - List directory")
        print("  status             - Server status")
        print("  exit               - Exit")
        print("-" * 60)

        # Loop interativo
        while self._running:
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, input, "\n> "
                )
                line = line.strip()

                if not line:
                    continue

                parts = line.split(maxsplit=1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                await self._handle_command(cmd, args)

            except EOFError:
                break
            except KeyboardInterrupt:
                break

        # Cleanup
        await self.client.disconnect()
        connect_task.cancel()

    async def _handle_command(self, cmd: str, args: str):
        """Executa comando do usuário."""
        try:
            if cmd == "exit":
                self._running = False
                return

            elif cmd == "chat":
                if not args:
                    print("[ERROR] Usage: chat <message>")
                    return
                print("[SENDING] Chat message...")
                response = await self.client.send_chat(args)
                print(f"\n[RESPONSE]\n{response.content}")

            elif cmd == "cmd":
                if not args:
                    print("[ERROR] Usage: cmd <command>")
                    return
                print(f"[RUNNING] {args}...")
                result = await self.client.run_command(args, timeout=30)
                if result.stdout:
                    print(f"\n[STDOUT]\n{result.stdout}")
                if result.stderr:
                    print(f"\n[STDERR]\n{result.stderr}")
                print(f"\n[EXIT CODE] {result.return_code}")

            elif cmd == "cat":
                if not args:
                    print("[ERROR] Usage: cat <file>")
                    return
                print(f"[READING] {args}...")
                result = await self.client.read_file(args)
                if result.exists:
                    print(f"\n[CONTENT]\n{result.content}")
                else:
                    print("[ERROR] File not found")

            elif cmd == "echo":
                parts = args.split(maxsplit=1)
                if len(parts) < 2:
                    print("[ERROR] Usage: echo <file> <content>")
                    return
                file_path, content = parts
                print(f"[WRITING] {file_path}...")
                result = await self.client.write_file(file_path, content)
                print(f"[OK] Written {result.bytes_written} bytes")

            elif cmd == "ls":
                path = args or "."
                print(f"[LISTING] {path}...")
                result = await self.client.list_directory(path)
                print("\nDirectories:")
                for d in result.directories:
                    print(f"  [DIR]  {d}")
                print("\nFiles:")
                for f in result.files:
                    print(f"  [FILE] {f}")

            elif cmd == "status":
                result = await self.client.get_status()
                print(f"\nServer Status: {result.server_status}")
                print(f"Active Sessions: {result.active_sessions}")

            else:
                print(f"[ERROR] Unknown command: {cmd}")

        except Exception as e:
            print(f"[ERROR] {e}")

    def _on_connect(self):
        print("\n[INFO] Connected to server")

    def _on_disconnect(self):
        print("\n[INFO] Disconnected from server")
        self._running = False

    def _on_error(self, e: Exception):
        print(f"\n[ERROR] {e}")


async def run_interactive():
    """Executa cliente interativo."""
    client = InteractiveClient(
        server_url=settings.server_url,
        client_id=settings.client_id,
        secret_key=settings.secret_key
    )
    await client.run()


async def run_once(server_url: str, client_id: str, secret_key: str, action: str, arg: str):
    """Executa ação única e sai."""
    client = RemoteClient(
        server_url=server_url,
        client_id=client_id,
        secret_key=secret_key
    )

    try:
        # Conecta
        connect_task = asyncio.create_task(client.connect())
        await asyncio.sleep(2)

        if not client.is_authenticated:
            print("[ERROR] Authentication failed")
            return

        # Executa ação
        if action == "chat":
            response = await client.send_chat(arg)
            print(response.content)

        elif action == "cmd":
            result = await client.run_command(arg, timeout=30)
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            sys.exit(result.return_code)

        elif action == "cat":
            result = await client.read_file(arg)
            if result.exists:
                print(result.content)
            else:
                print("[ERROR] File not found", file=sys.stderr)
                sys.exit(1)

        elif action == "write":
            parts = arg.split(maxsplit=1)
            if len(parts) < 2:
                print("[ERROR] Usage: write <file> <content>")
                sys.exit(1)
            result = await client.write_file(parts[0], parts[1])
            print(f"Written {result.bytes_written} bytes")

        elif action == "ls":
            result = await client.list_directory(arg or ".")
            for d in result.directories:
                print(f"[DIR]  {d}")
            for f in result.files:
                print(f"[FILE] {f}")

        else:
            print(f"[ERROR] Unknown action: {action}")
            sys.exit(1)

    finally:
        await client.disconnect()
        connect_task.cancel()


def main():
    """Entry point CLI."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Claude Remote Client"
    )
    parser.add_argument(
        "--server", "-s",
        default=settings.server_url,
        help="Server URL"
    )
    parser.add_argument(
        "--client-id", "-i",
        default=settings.client_id,
        help="Client ID"
    )
    parser.add_argument(
        "--secret", "-k",
        default=settings.secret_key,
        help="Secret key"
    )
    parser.add_argument(
        "--action", "-a",
        choices=["chat", "cmd", "cat", "write", "ls"],
        help="Action to execute (non-interactive mode)"
    )
    parser.add_argument(
        "--arg",
        help="Argument for action"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run in interactive mode"
    )
    parser.add_argument(
        "--log-level",
        default=settings.log_level,
        help="Log level"
    )

    args = parser.parse_args()

    # Override settings
    settings.server_url = args.server
    settings.client_id = args.client_id
    settings.secret_key = args.secret
    settings.log_level = args.log_level

    if args.interactive or (args.action is None and args.arg is None):
        # Interactive mode
        asyncio.run(run_interactive())
    else:
        # One-shot mode
        asyncio.run(run_once(
            args.server,
            args.client_id,
            args.secret,
            args.action,
            args.arg
        ))


if __name__ == "__main__":
    main()
