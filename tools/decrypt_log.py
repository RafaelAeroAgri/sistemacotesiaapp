#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script utilitário para descriptografar logs de voo gerados pelo Sistema Cotesia.

Uso:
    python decrypt_log.py path/do/log.enc path/da/chave.key output.txt
"""

import sys
from pathlib import Path

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("❌ Biblioteca 'cryptography' não encontrada. Instale com: pip install cryptography")
    sys.exit(1)


def main():
    if len(sys.argv) != 4:
        print("Uso: python decrypt_log.py LOG_ENCRIPTADO.enc CHAVE.key SAIDA.txt")
        sys.exit(1)

    arquivo_log = Path(sys.argv[1])
    arquivo_chave = Path(sys.argv[2])
    destino = Path(sys.argv[3])

    if not arquivo_log.exists():
        print(f"❌ Log não encontrado: {arquivo_log}")
        sys.exit(1)

    if not arquivo_chave.exists():
        print(f"❌ Chave não encontrada: {arquivo_chave}")
        sys.exit(1)

    key = arquivo_chave.read_bytes().strip()
    fernet = Fernet(key)

    dados = arquivo_log.read_bytes()
    conteudo = fernet.decrypt(dados)
    destino.write_bytes(conteudo)

    print(f"✅ Log descriptografado com sucesso em: {destino}")


if __name__ == "__main__":
    main()


