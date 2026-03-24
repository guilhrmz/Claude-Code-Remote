"""
Exemplo completo de uso do Claude Remote System.
Demonstra todas as funcionalidades do cliente.
"""

import asyncio
import logging
from client.ws_client import RemoteClient

# Configurar logging
logging.basicConfig(level=logging.INFO)


async def demo_completa():
    """Demonstra todas as funcionalidades."""

    # Configurar cliente
    client = RemoteClient(
        server_url="ws://localhost:8765",
        client_id="default_client",
        secret_key="default_secret"
    )

    print("=" * 60)
    print("Claude Remote System - Demo Completa")
    print("=" * 60)

    # Callbacks
    async def on_connect():
        print("\n[✓] Conectado ao servidor!")

    async def on_disconnect():
        print("\n[!] Desconectado do servidor")

    async def on_error(e):
        print(f"\n[ERRO] {e}")

    client.on_connect(on_connect)
    client.on_disconnect(on_disconnect)
    client.on_error(on_error)

    # Conectar
    print("\n[INFO] Conectando...")
    connect_task = asyncio.create_task(client.connect())

    # Aguardar conexão
    await asyncio.sleep(3)

    if not client.is_authenticated:
        print("[ERRO] Falha na autenticação")
        connect_task.cancel()
        return

    print("\n" + "=" * 60)
    print("DEMONSTRAÇÃO DAS FUNCIONALIDADES")
    print("=" * 60)

    # 1. Chat com Claude
    print("\n--- 1. CHAT COM CLAUDE ---")
    print("\n[ENVIO] Criando um arquivo Python...")

    response = await client.send_chat(
        content="Crie um código Python simples que imprime 'Hello World'",
        system_prompt="Você é um assistente de programação. Seja conciso."
    )

    print(f"\n[RESPOSTA]\n{response.content}")
    print(f"\n[SESSION_ID] {response.session_id}")

    # 2. Executar comando shell
    print("\n--- 2. EXECUTAR COMANDO SHELL ---")
    print("\n[ENVIO] ls -la")

    cmd_result = await client.run_command("ls -la", timeout=30)

    if cmd_result.stdout:
        print(f"\n[STDOUT]\n{cmd_result.stdout}")
    if cmd_result.stderr:
        print(f"\n[STDERR]\n{cmd_result.stderr}")
    print(f"[EXIT CODE] {cmd_result.return_code}")

    # 3. Escrever arquivo
    print("\n--- 3. ESCREVER ARQUIVO ---")

    codigo_python = '''
def hello_world():
    """Função simples de Hello World."""
    print("Hello, World!")
    return True

if __name__ == "__main__":
    hello_world()
'''

    write_result = await client.write_file(
        file_path="hello.py",
        content=codigo_python
    )

    print(f"[OK] Arquivo criado: {write_result.file_path}")
    print(f"[OK] Bytes escritos: {write_result.bytes_written}")

    # 4. Ler arquivo
    print("\n--- 4. LER ARQUIVO ---")

    file_content = await client.read_file("hello.py")

    if file_content.exists:
        print(f"\n[CONTEÚDO de hello.py]\n{file_content.content}")
    else:
        print("[ERRO] Arquivo não encontrado")

    # 5. Listar diretório
    print("\n--- 5. LISTAR DIRETÓRIO ---")

    dir_listing = await client.list_directory(".", recursive=False)

    print(f"\nDiretório: {dir_listing.path}")
    print("\nSubdiretórios:")
    for d in dir_listing.directories:
        print(f"  [DIR]  {d}")

    print("\nArquivos:")
    for f in dir_listing.files:
        print(f"  [FILE] {f}")

    # 6. Executar o arquivo criado
    print("\n--- 6. EXECUTAR ARQUIVO CRIADO ---")

    cmd_result = await client.run_command("python3 hello.py", timeout=10)

    if cmd_result.stdout:
        print(f"\n[OUTPUT]\n{cmd_result.stdout}")

    # 7. Verificar status do servidor
    print("\n--- 7. STATUS DO SERVIDOR ---")

    status = await client.get_status()

    print(f"Status: {status.server_status}")
    print(f"Sessões ativas: {status.active_sessions}")

    # 8. Manter sessão e enviar mais mensagens
    print("\n--- 8. CONTINUAR CONVERSA (SESSION) ---")

    # Enviar segunda mensagem na mesma sessão
    response2 = await client.send_chat(
        content="Agora adicione uma função que soma dois números",
        session_id=response.session_id  # Reutilizar sessão
    )

    print(f"\n[RESPOSTA]\n{response2.content}")

    # Finalizar
    print("\n" + "=" * 60)
    print("DEMONSTRAÇÃO COMPLETA!")
    print("=" * 60)

    # Cleanup
    await client.disconnect()
    connect_task.cancel()

    print("\n[INFO] Demo finalizada.")


async def demo_chat_continuo():
    """Demo de conversa contínua (chat session)."""

    client = RemoteClient(
        server_url="ws://localhost:8765",
        client_id="default_client",
        secret_key="default_secret"
    )

    client.on_connect(lambda: print("[CONNECTED]"))
    client.on_disconnect(lambda: print("[DISCONNECTED]"))

    connect_task = asyncio.create_task(client.connect())
    await asyncio.sleep(3)

    if not client.is_authenticated:
        print("[ERROR] Auth failed")
        return

    print("\n=== CONVERSA CONTÍNUA ===\n")

    session_id = None

    # Turno 1
    print("Q: O que é Python?")
    resp = await client.send_chat("O que é Python? Explique em 2 frases")
    print(f"A: {resp.content}\n")
    session_id = resp.session_id

    # Turno 2 (continua na mesma sessão)
    print("Q: Quais são os principais usos?")
    resp = await client.send_chat(
        "Quais são os principais usos de Python?",
        session_id=session_id
    )
    print(f"A: {resp.content}\n")

    # Turno 3
    print("Q: Mostre um exemplo de código")
    resp = await client.send_chat(
        "Mostre um exemplo de código Python simples",
        session_id=session_id
    )
    print(f"A: {resp.content}\n")

    await client.disconnect()
    connect_task.cancel()


async def demo_apenas_comandos():
    """Demo focada em comandos shell."""

    client = RemoteClient(
        server_url="ws://localhost:8765",
        client_id="default_client",
        secret_key="default_secret"
    )

    connect_task = asyncio.create_task(client.connect())
    await asyncio.sleep(3)

    if not client.is_authenticated:
        return

    print("\n=== DEMO DE COMANDOS ===\n")

    # Lista de comandos para demonstrar
    comandos = [
        "pwd",
        "uname -a",
        "python3 --version",
        "ls -la",
        "echo 'Teste remoto funcionou!' > teste.txt",
        "cat teste.txt",
        "rm teste.txt",
    ]

    for cmd in comandos:
        print(f"\n[CMD] {cmd}")
        result = await client.run_command(cmd, timeout=30)
        if result.stdout:
            print(f"[OUT] {result.stdout.strip()}")
        if result.stderr:
            print(f"[ERR] {result.stderr.strip()}")

    await client.disconnect()
    connect_task.cancel()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Demo do Claude Remote System")
    parser.add_argument(
        "--demo",
        choices=["completa", "chat", "comandos"],
        default="completa",
        help="Tipo de demonstração"
    )

    args = parser.parse_args()

    if args.demo == "completa":
        asyncio.run(demo_completa())
    elif args.demo == "chat":
        asyncio.run(demo_chat_continuo())
    elif args.demo == "comandos":
        asyncio.run(demo_apenas_comandos())
