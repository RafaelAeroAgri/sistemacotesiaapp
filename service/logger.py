#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de logging para o Sistema Cotesia
Configuração de logging profissional com rotação de arquivos
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import platform


def configurar_logging(pasta_logs=None):
    """
    Configura sistema de logging profissional
    - Logs detalhados em arquivo único por DIA (continua após RESET)
    - Logs importantes no console
    - Máximo 10 arquivos (rotativo)
    - Funciona offline e em qualquer local
    
    Args:
        pasta_logs: Caminho para pasta de logs (opcional)
    
    Returns:
        logger: Objeto logger configurado
    """
    # Determina pasta de logs com múltiplos fallbacks
    if pasta_logs is None:
        pasta_logs = _determinar_pasta_logs()
    
    # Nome do arquivo: UM POR DIA (continua gravando no mesmo após RESET)
    agora = datetime.now()
    nome_arquivo = agora.strftime('cotesia_%Y%m%d.log')  # SEM hora/minuto!
    caminho_log = os.path.join(pasta_logs, nome_arquivo)
    
    # Remove handlers antigos (evita duplicação)
    logger = logging.getLogger()
    logger.handlers.clear()
    
    # Configura formato detalhado
    formato_arquivo = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    formato_console = logging.Formatter(
        '%(levelname)s: %(message)s'
    )
    
    # Handler para arquivo (todos os detalhes)
    file_handler = RotatingFileHandler(
        caminho_log,
        maxBytes=10*1024*1024,  # 10MB por arquivo
        backupCount=10,          # Mantém 10 arquivos
        encoding='utf-8',
        mode='a'                 # APPEND - continua escrevendo no mesmo arquivo
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formato_arquivo)
    
    # Handler para console (apenas importante)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formato_console)
    
    # Configura logger raiz
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Log inicial com separador
    logger.info("="*60)
    logger.info("SISTEMA COTESIA - SESSÃO INICIADA")
    logger.info("="*60)
    logger.info(f"Arquivo de log: {caminho_log}")
    logger.info(f"Pasta de logs: {pasta_logs}")
    logger.info(f"Versão Python: {sys.version.split()[0]}")
    logger.info(f"Sistema: {platform.system()} {platform.release()}")
    logger.info(f"Modo: {'Executável' if getattr(sys, 'frozen', False) else 'Desenvolvimento'}")
    
    return logger


def _determinar_pasta_logs():
    """
    Determina a melhor pasta para salvar logs
    
    Returns:
        str: Caminho da pasta de logs
    """
    caminhos_possiveis = []
    
    if getattr(sys, 'frozen', False):
        # Executável
        caminhos_possiveis.append(os.path.join(os.path.dirname(sys.executable), 'logs'))
    else:
        # Desenvolvimento
        caminhos_possiveis.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs'))
    
    # Fallbacks garantidos (sempre funcionam)
    caminhos_possiveis.append(os.path.join(os.path.expanduser("~"), 'cotesia_logs'))
    caminhos_possiveis.append('/tmp/cotesia_logs')
    
    # Tenta criar pasta em cada caminho
    for caminho in caminhos_possiveis:
        try:
            if not os.path.exists(caminho):
                os.makedirs(caminho, exist_ok=True)
            # Testa se pode escrever
            teste_file = os.path.join(caminho, '.test_write')
            with open(teste_file, 'w') as f:
                f.write('test')
            os.remove(teste_file)
            return caminho
        except Exception:
            continue
    
    # Último recurso: /tmp
    return '/tmp'


def adicionar_log_voo(logger, pasta_voo, numero_voo, nome_arquivo=None):
    """
    Adiciona handler de logging específico para a pasta do voo
    Grava LOG_VOO_X.txt dentro da pasta do voo
    
    Args:
        logger: Objeto logger
        pasta_voo: Caminho da pasta do voo
        numero_voo: Número do voo
    
    Returns:
        handler: Handler do arquivo de log do voo
    """
    try:
        # Cria arquivo de log específico do voo
        nome_arquivo = nome_arquivo or f"LOG_VOO_{numero_voo}.txt"
        arquivo_log_voo = os.path.join(pasta_voo, nome_arquivo)
        
        # Formato para log do voo (mais limpo para cliente)
        formato_voo = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Cria handler para arquivo do voo
        handler_log_voo = logging.FileHandler(
            arquivo_log_voo,
            mode='a',
            encoding='utf-8'
        )
        handler_log_voo.setLevel(logging.DEBUG)  # Captura tudo, inclusive HTTP
        handler_log_voo.setFormatter(formato_voo)
        
        # Adiciona ao logger
        logger.addHandler(handler_log_voo)
        
        # Log inicial no arquivo do voo
        logger.info("="*70)
        logger.info(f"LOG DO VOO_{numero_voo}")
        logger.info("="*70)
        logger.info(f"Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        logger.info(f"Arquivo: {arquivo_log_voo}")
        logger.info("="*70)
        
        logger.debug(f"Handler de log do voo adicionado: {arquivo_log_voo}")
        
        return handler_log_voo
        
    except Exception as e:
        logger.error(f"Erro ao adicionar log do voo: {e}")
        return None


def remover_log_voo(logger, handler_log_voo):
    """
    Remove o handler de logging do voo atual
    
    Args:
        logger: Objeto logger
        handler_log_voo: Handler do log do voo
    """
    try:
        if handler_log_voo is not None:
            logger.info("="*70)
            logger.info("FIM DO REGISTRO DESTE VOO")
            logger.info("="*70)
            logger.removeHandler(handler_log_voo)
            handler_log_voo.close()
            logger.debug("Handler de log do voo removido")
    except Exception as e:
        logger.error(f"Erro ao remover log do voo: {e}")

