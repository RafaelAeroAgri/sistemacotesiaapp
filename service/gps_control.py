#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de controle GPS e ciclos de voo para o Sistema Cotesia
Gerencia os 4 ciclos de operação e gravação de dados
"""

import time
import math
import os
import glob
import json
import serial
import pynmea2
import threading
import calendar
from datetime import datetime
import pytz
import simplekml
import shutil

try:
    from cryptography.fernet import Fernet
except ImportError:  # pragma: no cover
    Fernet = None

from logger import adicionar_log_voo, remover_log_voo


class GPSControl:
    """Controla o GPS e os ciclos de voo do sistema Cotesia"""
    
    def __init__(self, servo_control, logger=None, config=None):
        """
        Inicializa o controle de GPS
        
        Args:
            servo_control: Instância de ServoControl
            logger: Objeto logger (opcional)
            config: Dicionário de configurações
        """
        self.servo_control = servo_control
        self.logger = logger
        self.config = config or {}
        
        # Parâmetros configuráveis
        self.distancia_metros = self.config.get('distancia_metros', 25)
        self.tempo_parada = self.config.get('tempo_parada', 10)
        self.velocidade_operacao = self.config.get('velocidade_operacao', 5.0)
        self.precisao_minima_satelites = self.config.get('precisao_minima_satelites', 3)
        self.pdop_maximo = self.config.get('pdop_maximo', 6.0)
        self.first_movement_threshold = self.config.get('first_movement_threshold', 5.0)
        self.velocidade_parada = self.config.get('velocidade_parada', 1.5)
        
        # Estado do GPS
        self.gps_status = "DESCONECTADO"
        self.num_satelites = 0
        self.coordenadas_atuais = "Não disponível"
        self.ultima_velocidade = 0.0
        self.pdop_atual = 999.0
        self.gps_serial = None
        self.gps_port = None
        
        # Estado do sistema
        self.estado_sistema = "AGUARDANDO_SATELITES"
        self.ciclo_atual = 0
        self.finalizado = False
        
        # Posição e distância
        self.ultima_posicao = None
        self.distancia_acumulada = 0.0
        self.tempo_parada_atual = 0.0
        self.ultima_verificacao_parada = None
        
        # Voo
        self.numero_voo = 0
        self.numero_voo_diario = 0
        self.pasta_voo_atual = ""
        self.pasta_backup = os.path.join(os.path.expanduser("~"), "cotesia_backup")
        os.makedirs(self.pasta_backup, exist_ok=True)
        self.metadata_voo = {}
        self.flight_log_handler = None
        self.data_voo = None
        self.data_inicio_voo_iso = None
        
        # Estatísticas
        self.velocidades_registradas = []
        self.tempo_inicio_voo = None
        self.tempo_fim_voo = None
        self.data_inicio_voo = None
        
        # Thread
        self.thread_gps = None
        self.rodando = False
        
        # Simulação
        self.modo_simulacao = False
        self.thread_simulacao = None
        self.velocidade_media_simulacao = 12
        self._frequencia_gps_hz = self.config.get('gps.frequency_hz', 5)
        self._frequencias_disponiveis = self.config.get('gps.available_frequencies', list(range(1, 11)))
        
        self._log("GPSControl inicializado")
    
    def _log(self, mensagem, level="info"):
        """Log interno com fallback para print"""
        if self.logger:
            getattr(self.logger, level)(mensagem)
        else:
            print(f"[GPS] {mensagem}")
    
    def iniciar(self):
        """Inicia a thread de leitura do GPS"""
        if self.rodando:
            self._log("GPS já está rodando")
            return False
        
        self.rodando = True
        self.thread_gps = threading.Thread(target=self._thread_gps, daemon=True)
        self.thread_gps.start()
        self._log("Thread GPS iniciada")
        return True
    
    def parar(self):
        """Para a thread de leitura do GPS"""
        self.rodando = False
        if self.gps_serial:
            try:
                self.gps_serial.close()
            except:
                pass
        self._log("Thread GPS parada")
    
    def get_status(self):
        """Retorna status completo do sistema"""
        return {
            'gps_status': self.gps_status,
            'num_satelites': self.num_satelites,
            'coordenadas': self.coordenadas_atuais,
            'velocidade_ms': round(self.ultima_velocidade, 2),
            'velocidade_kmh': round(self.ultima_velocidade * 3.6, 2),
            'pdop': round(self.pdop_atual, 2),
            'estado_sistema': self.estado_sistema,
            'ciclo_atual': self.ciclo_atual,
            'distancia_acumulada': round(self.distancia_acumulada, 2),
            'tempo_parada_atual': round(self.tempo_parada_atual, 2),
            'numero_voo': self.numero_voo,
            'servos_ativacoes': self.servo_control.contador_ativacoes,
            'finalizado': self.finalizado,
            'modo_simulacao': self.modo_simulacao,
            'gps_frequency_hz': self._frequencia_gps_hz,
        }
    
    def get_config(self):
        """Retorna configurações atuais"""
        return {
            'distancia_metros': self.distancia_metros,
            'tempo_parada': self.tempo_parada,
            'velocidade_operacao': self.velocidade_operacao,
            'precisao_minima_satelites': self.precisao_minima_satelites
        }
    
    def set_config(self, config):
        """Atualiza configurações"""
        if 'distancia_metros' in config:
            self.distancia_metros = config['distancia_metros']
        if 'tempo_parada' in config:
            self.tempo_parada = config['tempo_parada']
        if 'velocidade_operacao' in config:
            self.velocidade_operacao = config['velocidade_operacao']
        self._log(f"Configurações atualizadas: {config}")
        return True
    
    def iniciar_voo(self):
        """Inicia o ciclo de voo (apenas se satélites >= 3)"""
        if self.num_satelites < self.precisao_minima_satelites:
            self._log(f"Não é possível iniciar: apenas {self.num_satelites} satélites (necessário >= {self.precisao_minima_satelites})", "warning")
            return False
        
        if self.ciclo_atual != 0:
            self._log("Voo já foi iniciado", "warning")
            return False
        
        # Força início do voo
        self._log("INÍCIO DE VOO FORÇADO VIA API")
        self.estado_sistema = "OPERANDO"
        return True
    
    def parar_voo(self):
        """Para o voo manualmente"""
        self._log("PARADA MANUAL DE VOO")
        self._finalizar_voo()
        return True
    
    def _preparar_voo(self):
        """Configura variáveis iniciais para um novo voo ou simulação"""
        self._log("Preparando voo (resetando contadores e criando pasta)")
        self.finalizado = False
        self.estado_sistema = "PREPARANDO"
        self.ciclo_atual = 0
        self.distancia_acumulada = 0.0
        self.tempo_parada_atual = 0.0
        self.ultima_verificacao_parada = None
        self.ultima_posicao = None
        self.velocidades_registradas = []
        self.servo_control.contador_ativacoes = 0
        self.tempo_inicio_voo = time.time()
        self.data_inicio_voo = datetime.now(
            pytz.timezone('America/Sao_Paulo')
        ).strftime('%d/%m/%Y %H:%M:%S')
        self._criar_pasta_voo()
    
    def resetar_sistema(self):
        """Reseta o sistema para o estado inicial"""
        self._log("RESETANDO SISTEMA COMPLETO")
        
        self.finalizado = False
        self.estado_sistema = "AGUARDANDO_SATELITES"
        self.ciclo_atual = 0
        self.distancia_acumulada = 0.0
        self.tempo_parada_atual = 0.0
        self.ultima_verificacao_parada = None
        self.ultima_posicao = None
        self.velocidades_registradas = []
        self.tempo_inicio_voo = None
        self.tempo_fim_voo = None
        self.data_inicio_voo = None
        self.servo_control.contador_ativacoes = 0
        self.pasta_voo_atual = ""
        self.metadata_voo = {}
        self.numero_voo_diario = 0
        self.data_voo = None
        self.data_inicio_voo_iso = None
        
        if self.logger and self.flight_log_handler:
            remover_log_voo(self.logger, self.flight_log_handler)
            self.flight_log_handler = None
        
        # Reset servos
        self.servo_control.reset()
        
        self._log("Sistema resetado")
        return True
    
    def _thread_gps(self):
        """Thread principal de leitura e processamento do GPS"""
        ultima_tentativa_conexao = 0
        ultima_leitura_gps = 0
        timeout_sem_dados = 15  # segundos
        nova_posicao = None
        ultima_atualizacao = time.time()
        ultimo_log_ciclo0 = 0
        ultimo_pdop_log = 0
        posicao_alternada = False
        
        while self.rodando:
            if self.finalizado:
                time.sleep(1)
                continue
            
            try:
                tempo_atual = time.time()
                
                # Tenta conectar ao GPS se desconectado
                if self.gps_status == "DESCONECTADO":
                    if tempo_atual - ultima_tentativa_conexao >= 2:
                        ultima_tentativa_conexao = tempo_atual
                        if self._tentar_conectar_gps():
                            ultima_leitura_gps = time.time()
                    else:
                        time.sleep(0.1)
                        continue
                
                if self.gps_status == "DESCONECTADO":
                    time.sleep(0.1)
                    continue
                
                # Detecta GPS travado
                if self.gps_serial and ultima_leitura_gps > 0:
                    tempo_sem_dados = time.time() - ultima_leitura_gps
                    if tempo_sem_dados > timeout_sem_dados:
                        self._log(f"🚨 GPS TRAVADO: Sem dados há {tempo_sem_dados:.1f}s!", "error")
                        self._desconectar_gps()
                        continue
                
                # Lê dados do GPS
                try:
                    if self.gps_serial and self.gps_serial.in_waiting:
                        linha = self.gps_serial.readline().decode('ascii', errors='ignore').strip()
                        
                        if not linha:
                            continue
                        
                        ultima_leitura_gps = time.time()
                        
                        if linha.startswith("$GPGGA"):
                            msg = pynmea2.parse(linha)
                            if msg.num_sats is not None:
                                self.num_satelites = int(msg.num_sats)
                            if msg.latitude and msg.longitude:
                                nova_posicao = (msg.latitude, msg.longitude)
                                self.coordenadas_atuais = f"{msg.latitude:.6f}, {msg.longitude:.6f}"
                        
                        elif linha.startswith("$GPRMC"):
                            msg = pynmea2.parse(linha)
                            if msg.spd_over_grnd is not None:
                                self.ultima_velocidade = msg.spd_over_grnd * 0.514444  # Nós para m/s
                        
                        elif linha.startswith("$GPGSA"):
                            msg = pynmea2.parse(linha)
                            if msg.pdop:
                                self.pdop_atual = float(msg.pdop)
                
                except serial.SerialException:
                    self._log("🚨 GPS DESCONECTOU durante voo!", "error")
                    self._desconectar_gps()
                    continue
                except Exception as e:
                    self._log(f"Erro ao ler dados: {e}", "debug")
                    continue
                
                # PROCESSAMENTO DOS CICLOS
                if nova_posicao is None:
                    continue
                
                if self.ultima_posicao is None:
                    self.ultima_posicao = nova_posicao
                    continue
                
                # Verifica qualidade do GPS
                gps_confiavel = (self.gps_status == "CONECTADO" and 
                               self.num_satelites >= self.precisao_minima_satelites and 
                               self.pdop_atual <= self.pdop_maximo)
                
                # CICLO 0: Aguardando movimento inicial
                if self.ciclo_atual == 0:
                    if not gps_confiavel:
                        tempo_desde_ultimo_log = tempo_atual - ultimo_log_ciclo0
                        pdop_mudou = abs(self.pdop_atual - ultimo_pdop_log) >= 0.5
                        
                        if tempo_desde_ultimo_log >= 5 or pdop_mudou:
                            self._log(f"CICLO 0: Aguardando GPS melhorar (Sats: {self.num_satelites}, PDOP: {self.pdop_atual:.1f})")
                            ultimo_log_ciclo0 = tempo_atual
                            ultimo_pdop_log = self.pdop_atual
                        continue
                    
                    if self.ultima_velocidade >= self.first_movement_threshold:
                        self._log(f"CICLO 0→1: Movimento iniciado ({self.ultima_velocidade:.1f} m/s)")
                        self.ciclo_atual = 1
                        self.estado_sistema = "OPERANDO"
                        self.tempo_inicio_voo = time.time()
                        tz = pytz.timezone('America/Sao_Paulo')
                        self.data_voo = datetime.now(tz)
                        self.data_inicio_voo = self.data_voo.strftime('%d/%m/%Y %H:%M:%S')
                        self.data_inicio_voo_iso = self.data_voo.isoformat()
                
                # CICLO 1: Aguardando primeira parada
                elif self.ciclo_atual == 1:
                    if not gps_confiavel:
                        self._log(f"⚠️ CICLO 1: GPS degradado - continuando", "warning")
                    
                    if self.ultima_velocidade <= self.velocidade_parada:
                        self._log(f"CICLO 1→2: Primeira parada ({self.ultima_velocidade:.1f} m/s)")
                        
                        # Cria pasta do voo
                        self._criar_pasta_voo()
                        self._gravar_coordenada(nova_posicao)
                        
                        # Primeiro lançamento
                        self.servo_control.mover_operacao(True)
                        
                        self.ciclo_atual = 2
                        self.distancia_acumulada = 0
                        self.ultima_posicao = nova_posicao
                        self._log("CICLO 1→2: Primeira parada, primeiro lançamento realizado")
                
                # CICLO 2: Primeira parada - aguarda retomar velocidade
                elif self.ciclo_atual == 2:
                    if self.ultima_velocidade >= self.velocidade_operacao:
                        self._log(f"CICLO 2→3: Velocidade retomada ({self.ultima_velocidade:.1f} m/s)")
                        self.ciclo_atual = 3
                        self.distancia_acumulada = 0
                        self.ultima_posicao = nova_posicao
                        self.ultima_verificacao_parada = None
                        self.tempo_parada_atual = 0
                
                # CICLO 3: Operação normal
                elif self.ciclo_atual == 3:
                    # Registra velocidades
                    if tempo_atual - ultima_atualizacao >= 5:
                        self.velocidades_registradas.append(self.ultima_velocidade)
                        ultima_atualizacao = tempo_atual
                    
                    # Velocidade >= threshold: em operação
                    if self.ultima_velocidade >= self.velocidade_operacao:
                        if self.ultima_verificacao_parada is not None:
                            self._log(f"Velocidade retomada - resetando contador ({self.ultima_velocidade:.1f} m/s)")
                            self.ultima_verificacao_parada = None
                            self.tempo_parada_atual = 0
                        
                        # Calcula distância percorrida
                        if gps_confiavel:
                            distancia_delta = self._calcular_distancia(self.ultima_posicao, nova_posicao)
                            
                            if distancia_delta < 100:  # Validação: ignora saltos > 100m
                                self.distancia_acumulada += distancia_delta
                                self.ultima_posicao = nova_posicao
                                
                                # Verifica se atingiu distância alvo
                                if self.distancia_acumulada >= self.distancia_metros:
                                    self._log(f"Distância atingida: {self.distancia_acumulada:.1f}m >= {self.distancia_metros}m")
                                    self._gravar_coordenada(nova_posicao)
                                    self.servo_control.mover_operacao(posicao_alternada)
                                    posicao_alternada = not posicao_alternada
                                    self.distancia_acumulada = 0
                    
                    # Velocidade < threshold: iniciando parada
                    else:
                        if self.ultima_verificacao_parada is None:
                            self._log(f"Velocidade baixa - iniciando contador ({self.ultima_velocidade:.1f} m/s)")
                            self.ultima_verificacao_parada = time.time()
                        
                        self.tempo_parada_atual = time.time() - self.ultima_verificacao_parada
                        
                        # Verifica se atingiu tempo de parada
                        if self.tempo_parada_atual >= self.tempo_parada:
                            self._log(f"CICLO 3→FIM: Parada confirmada ({self.tempo_parada_atual:.1f}s)")
                            self._finalizar_voo()
            
            except Exception as e:
                self._log(f"Erro na thread GPS: {e}", "error")
                time.sleep(0.1)
    
    def _tentar_conectar_gps(self):
        """Tenta conectar ao GPS em todas as portas disponíveis"""
        portas = self._detectar_portas_seriais()
        
        for porta in portas:
            try:
                self.gps_serial = serial.Serial(porta, 9600, timeout=1)
                self.gps_port = porta
                self.gps_status = "CONECTADO"
                self._log(f"GPS CONECTADO: {porta}")
                
                # Limpa buffers
                try:
                    self.gps_serial.reset_input_buffer()
                    self.gps_serial.reset_output_buffer()
                    time.sleep(0.2)
                except:
                    pass
                
                return True
            except Exception as e:
                continue
        
        return False
    
    def _desconectar_gps(self):
        """Desconecta do GPS"""
        self.gps_status = "DESCONECTADO"
        if self.gps_serial:
            try:
                self.gps_serial.close()
            except:
                pass
        self.gps_serial = None
    
    def _detectar_portas_seriais(self):
        """Detecta portas seriais disponíveis"""
        portas = []
        
        try:
            portas.extend(glob.glob('/dev/ttyUSB*'))
            portas.extend(glob.glob('/dev/ttyACM*'))
            portas.extend(glob.glob('/dev/ttyS*'))
            portas.extend(glob.glob('/dev/ttyAMA*'))
            
            if os.path.exists('/dev/serial0'):
                portas.append('/dev/serial0')
        except Exception as e:
            self._log(f"Erro ao detectar portas: {e}", "error")
        
        return portas or ['/dev/ttyUSB0', '/dev/ttyACM0']
    
    def _calcular_distancia(self, pos1, pos2):
        """Calcula distância entre duas coordenadas (Haversine)"""
        if not pos1 or not pos2:
            return 0.0
        
        try:
            lat1, lon1 = pos1
            lat2, lon2 = pos2
            
            lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
            
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))
            r = 6371000  # Raio da Terra em metros
            
            return c * r
        except Exception as e:
            self._log(f"Erro ao calcular distância: {e}", "error")
            return 0.0
    
    def _criar_pasta_voo(self):
        """Cria pasta para o voo atual seguindo estrutura ANO/MÊS/DIA/VOO_XX"""
        try:
            tz = pytz.timezone('America/Sao_Paulo')
            data_referencia = self.data_voo or datetime.now(tz)
            ano = f"{data_referencia.year}"
            mes_num = data_referencia.month
            mes_nome = calendar.month_name[mes_num].upper()
            dia = f"{data_referencia.day:02d}"

            pasta_dia = os.path.join(self.pasta_backup, ano, mes_nome, dia)
            os.makedirs(pasta_dia, exist_ok=True)

            # Número sequencial do dia
            existentes = glob.glob(os.path.join(pasta_dia, "VOO_*"))
            if existentes:
                numeros_diarios = [
                    int(os.path.basename(p).split('_')[-1])
                    for p in existentes
                    if os.path.basename(p).split('_')[-1].isdigit()
                ]
                self.numero_voo_diario = max(numeros_diarios) + 1 if numeros_diarios else 1
            else:
                self.numero_voo_diario = 1

            # Número global sequencial
            self.numero_voo = self._obter_proximo_numero_global()

            pasta_voo_nome = f"VOO_{self.numero_voo_diario:02d}"
            self.pasta_voo_atual = os.path.join(pasta_dia, pasta_voo_nome)
            os.makedirs(self.pasta_voo_atual, exist_ok=True)

            data_iso = data_referencia.isoformat()
            data_humana = data_referencia.strftime('%d/%m/%Y %H:%M:%S')

            self.metadata_voo = {
                "id": f"{ano}-{mes_num:02d}-{dia}-VOO{self.numero_voo:04d}",
                "numero_global": self.numero_voo,
                "numero_diario": self.numero_voo_diario,
                "ano": int(ano),
                "mes": mes_num,
                "mes_nome": mes_nome,
                "dia": int(dia),
                "data_iso": data_iso,
                "data_humana": data_humana,
                "pasta_relativa": os.path.join(ano, mes_nome, dia, pasta_voo_nome),
                "arquivos": {
                    "coordenadas": f"VOO{self.numero_voo_diario:02d}.txt",
                    "percurso": f"PERCURSO{self.numero_voo_diario:02d}.kml",
                    "pontos": f"PONTOS{self.numero_voo_diario:02d}.kml",
                    "relatorio": f"DADOS{self.numero_voo_diario:02d}.txt",
                    "log": "LOG_COMPLETO.txt"
                },
                "log_encrypted": False,
            }
            self._salvar_metadata_voo()

            if self.logger:
                self.flight_log_handler = adicionar_log_voo(
                    self.logger,
                    self.pasta_voo_atual,
                    self.metadata_voo["id"],
                    nome_arquivo=self.metadata_voo["arquivos"]["log"]
                )

            self._log(f"Pasta do voo criada: {self.pasta_voo_atual}")
            return True
        except Exception as e:
            self._log(f"Erro ao criar pasta do voo: {e}", "error")
            return False
    
    def _gravar_coordenada(self, posicao):
        """Grava coordenada no arquivo do voo"""
        if not self.pasta_voo_atual:
            return
        
        try:
            coordenadas_nome = self.metadata_voo.get('arquivos', {}).get(
                'coordenadas',
                f"VOO{self.numero_voo_diario:02d}.txt"
            )
            arquivo = os.path.join(self.pasta_voo_atual, coordenadas_nome)
            lat, lon = posicao
            
            with open(arquivo, "a") as f:
                f.write(f"{lat:.6f}, {lon:.6f}\n")
                f.flush()
                os.fsync(f.fileno())
            
            self._log(f"Coordenada gravada: {lat:.6f}, {lon:.6f}", "debug")
        except Exception as e:
            self._log(f"Erro ao gravar coordenada: {e}", "error")
    
    def _finalizar_voo(self):
        """Finaliza o voo e gera relatórios"""
        self.finalizado = True
        self.estado_sistema = "CONVERTENDO"
        self.tempo_fim_voo = time.time()
        
        # Reset servos
        self.servo_control.reset()
        
        # Gera arquivos
        self._gerar_kml()
        self._gerar_relatorio()
        
        # Calcula tamanho total dos arquivos
        tamanho_total = 0
        for arquivo in os.listdir(self.pasta_voo_atual or ""):
            caminho = os.path.join(self.pasta_voo_atual, arquivo)
            if os.path.isfile(caminho):
                tamanho_total += os.path.getsize(caminho)
        
        tz = pytz.timezone('America/Sao_Paulo')
        self._salvar_metadata_voo({
            "finalizado_em": datetime.now(tz).isoformat(),
            "modo_simulacao": self.modo_simulacao,
            "tamanho_mb": round(tamanho_total / 1024 / 1024, 2)
        })
        
        if self.logger and self.flight_log_handler:
            remover_log_voo(self.logger, self.flight_log_handler)
            self.flight_log_handler = None
        
        log_nome = self.metadata_voo.get('arquivos', {}).get('log')
        if log_nome:
            caminho_log = os.path.join(self.pasta_voo_atual, log_nome)
            self._tentar_criptografar_log(caminho_log)
        
        self.modo_simulacao = False
        
        self.estado_sistema = "FINALIZADO"
        self._log("✅ Voo finalizado com sucesso")
    
    def _gerar_kml(self):
        """Gera arquivos KML do percurso e pontos"""
        if not self.pasta_voo_atual:
            return
        
        try:
            coordenadas_nome = self.metadata_voo.get('arquivos', {}).get(
                'coordenadas',
                f"VOO{self.numero_voo_diario:02d}.txt"
            )
            arquivo_txt = os.path.join(self.pasta_voo_atual, coordenadas_nome)
            
            if not os.path.exists(arquivo_txt):
                self._log("Arquivo de coordenadas não encontrado", "warning")
                return
            
            # Lê coordenadas
            coordenadas = []
            with open(arquivo_txt, 'r') as f:
                for linha in f:
                    try:
                        lat, lon = map(float, linha.strip().split(','))
                        coordenadas.append((lon, lat))  # KML usa (lon, lat)
                    except:
                        continue
            
            if not coordenadas:
                self._log("Nenhuma coordenada válida encontrada", "warning")
                return
            
            # KML do percurso
            kml_percurso = simplekml.Kml()
            ls = kml_percurso.newlinestring(name=f"Percurso Voo {self.numero_voo}")
            ls.coords = coordenadas
            ls.style.linestyle.width = 3
            ls.style.linestyle.color = simplekml.Color.red
            percurso_nome = self.metadata_voo.get('arquivos', {}).get(
                'percurso',
                f"PERCURSO{self.numero_voo_diario:02d}.kml"
            )
            arquivo_percurso = os.path.join(self.pasta_voo_atual, percurso_nome)
            kml_percurso.save(arquivo_percurso)
            
            # KML dos pontos
            kml_pontos = simplekml.Kml()
            for coord in coordenadas:
                pnt = kml_pontos.newpoint(name="")
                pnt.coords = [coord]
                pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png'
            pontos_nome = self.metadata_voo.get('arquivos', {}).get(
                'pontos',
                f"PONTOS{self.numero_voo_diario:02d}.kml"
            )
            arquivo_pontos = os.path.join(self.pasta_voo_atual, pontos_nome)
            kml_pontos.save(arquivo_pontos)
            
            self._log(f"Arquivos KML gerados com {len(coordenadas)} pontos")
        except Exception as e:
            self._log(f"Erro ao gerar KML: {e}", "error")
    
    def _gerar_relatorio(self):
        """Gera relatório do voo"""
        if not self.pasta_voo_atual:
            return
        
        try:
            relatorio_nome = self.metadata_voo.get('arquivos', {}).get(
                'relatorio',
                f"DADOS{self.numero_voo_diario:02d}.txt"
            )
            arquivo = os.path.join(self.pasta_voo_atual, relatorio_nome)
            
            duracao = 0
            if self.tempo_fim_voo and self.tempo_inicio_voo:
                duracao = self.tempo_fim_voo - self.tempo_inicio_voo
            
            vel_media = 0
            if self.velocidades_registradas:
                vel_media = sum(self.velocidades_registradas) / len(self.velocidades_registradas)
            
            with open(arquivo, 'w', encoding='utf-8') as f:
                f.write("="*50 + "\n")
                f.write(f"  RELATÓRIO DE VOO - VOO_{self.numero_voo}\n")
                f.write("="*50 + "\n\n")
                f.write(f"Data: {datetime.now(pytz.timezone('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M:%S')}\n")
                f.write(f"Início do voo: {self.data_inicio_voo or 'N/A'}\n\n")
                f.write("INFORMAÇÕES OPERACIONAIS:\n")
                f.write("-"*30 + "\n")
                f.write(f"Distância entre tubos: {self.distancia_metros}m\n")
                f.write(f"Tubos lançados: {self.servo_control.contador_ativacoes}\n")
                f.write(f"Duração: {int(duracao//60)}min {int(duracao%60)}s\n\n")
                f.write("DADOS DE DESEMPENHO:\n")
                f.write("-"*30 + "\n")
                f.write(f"Velocidade média: {vel_media * 3.6:.1f} km/h\n")
                f.write(f"Distância percorrida: {self.servo_control.contador_ativacoes * self.distancia_metros}m\n\n")
                f.write("QUALIDADE DOS DADOS:\n")
                f.write("-"*30 + "\n")
                f.write(f"Satélites: {self.num_satelites}\n")
                f.write(f"PDOP médio: {self.pdop_atual:.2f}\n")
            
            self._log(f"Relatório gerado: {arquivo}")
            
            minutos = int(duracao // 60)
            segundos = int(duracao % 60)
            self._salvar_metadata_voo({
                "tubos": self.servo_control.contador_ativacoes,
                "duracao_segundos": duracao,
                "duracao_humana": f"{minutos}min {segundos}s",
                "velocidade_media_kmh": round(vel_media * 3.6, 2),
                "distancia_total_m": self.servo_control.contador_ativacoes * self.distancia_metros
            })
        except Exception as e:
            self._log(f"Erro ao gerar relatório: {e}", "error")
    
    def _obter_proximo_numero_global(self):
        """Descobre o próximo identificador global de voo"""
        try:
            meta_files = glob.glob(
                os.path.join(self.pasta_backup, "**", "metadata.json"),
                recursive=True
            )
            numeros = []
            for meta_file in meta_files:
                try:
                    with open(meta_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    valor = int(data.get('numero_global') or data.get('numero') or 0)
                    if valor:
                        numeros.append(valor)
                except Exception:
                    continue
            
            # Compatibilidade com estrutura antiga (VOO_X na raiz)
            pastas_antigas = glob.glob(os.path.join(self.pasta_backup, "VOO_*"))
            for pasta in pastas_antigas:
                try:
                    valor = int(os.path.basename(pasta).split('_')[-1])
                    numeros.append(valor)
                except Exception:
                    continue
            
            return max(numeros) + 1 if numeros else 1
        except Exception as e:
            self._log(f"Erro ao calcular número global: {e}", "warning")
            return 1
    
    def _salvar_metadata_voo(self, extra=None):
        """Atualiza arquivo de metadata do voo atual"""
        if not self.pasta_voo_atual:
            return
        
        try:
            if self.metadata_voo is None:
                self.metadata_voo = {}
            if extra:
                self.metadata_voo.update(extra)
            
            meta_path = os.path.join(self.pasta_voo_atual, "metadata.json")
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(self.metadata_voo, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._log(f"Erro ao salvar metadata do voo: {e}", "error")
    
    def _tentar_criptografar_log(self, arquivo_log):
        """Aplica criptografia ao log se houver chave configurada"""
        if not os.path.exists(arquivo_log):
            return
        if Fernet is None:
            self._log("Biblioteca 'cryptography' não instalada; log não foi criptografado", "warning")
            return
        
        chave_path = self.config.get('log_key_path') or os.path.join(os.path.expanduser("~"), ".cotesia_log.key")
        if not os.path.exists(chave_path):
            self._log("Chave de criptografia não encontrada (.cotesia_log.key)", "warning")
            return
        
        try:
            with open(chave_path, 'rb') as key_file:
                chave = key_file.read().strip()
            fernet = Fernet(chave)
        except Exception as e:
            self._log(f"Erro ao carregar chave de criptografia: {e}", "error")
            return
        
        try:
            with open(arquivo_log, 'rb') as f:
                conteudo = f.read()
            criptografado = fernet.encrypt(conteudo)
            arquivo_encrypted = f"{arquivo_log}.enc"
            with open(arquivo_encrypted, 'wb') as f:
                f.write(criptografado)
            os.remove(arquivo_log)
            
            arquivos = dict(self.metadata_voo.get('arquivos', {}))
            arquivos['log'] = os.path.basename(arquivo_encrypted)
            self._salvar_metadata_voo({
                "log_encrypted": True,
                "arquivos": arquivos
            })
            self._log("Log do voo criptografado com sucesso")
        except Exception as e:
            self._log(f"Erro ao criptografar log: {e}", "error")
    
    def iniciar_simulacao(self, velocidade_media=12):
        """
        Inicia uma simulação inteligente de voo com 20 tubos
        
        Args:
            velocidade_media: Velocidade média em m/s (padrão: 12)
        
        Returns:
            bool: True se iniciou com sucesso
        """
        # Verifica se já está em voo ou simulação
        if self.ciclo_atual > 0:
            self._log("Já há um voo/simulação em andamento", "warning")
            return False
        
        # Ativa modo simulação
        self.modo_simulacao = True
        self.velocidade_media_simulacao = velocidade_media
        
        # Inicia thread de simulação
        self.thread_simulacao = threading.Thread(
            target=self._thread_simulacao,
            daemon=True
        )
        self.thread_simulacao.start()
        
        self._log(f"Simulação iniciada - Velocidade média: {velocidade_media}m/s (20 tubos)")
        return True
    
    def _thread_simulacao(self):
        """Thread que simula um voo realista de 20 tubos"""
        import random
        
        try:
            # Simula GPS conectado com bons satélites
            self.gps_status = "CONECTADO"
            self.num_satelites = random.randint(8, 12)
            self.pdop_atual = random.uniform(1.5, 2.5)
            self.coordenadas_atuais = "-23.550520,-46.633308"  # Coordenada exemplo
            
            # Aguarda um pouco
            time.sleep(1)
            
            # Prepara voo
            self._preparar_voo()
            self.ciclo_atual = 1
            self.estado_sistema = "AGUARDANDO_MOVIMENTO"
            
            time.sleep(2)
            
            # Simula primeiro movimento (Ciclo 1 → 2)
            self._log("SIMULAÇÃO: Movimento detectado")
            self.ciclo_atual = 2
            self.estado_sistema = "EM_MOVIMENTO"
            self.ultima_posicao = (-23.550520, -46.633308)
            self.tempo_inicio_voo = time.time()
            
            # Ciclo 3: Operação - 20 tubos
            self.ciclo_atual = 3
            self.estado_sistema = "OPERACAO"
            
            posicao_alternada = False
            
            for tubo in range(20):
                # Variação inteligente de velocidade (±30% da média)
                variacao = random.uniform(0.7, 1.3)
                velocidade_atual = self.velocidade_media_simulacao * variacao
                self.ultima_velocidade = velocidade_atual
                
                # Calcula tempo para percorrer a distância
                tempo_percurso = self.distancia_metros / velocidade_atual
                
                # Simula o percurso gradualmente
                passos = 10
                for _ in range(passos):
                    if not self.modo_simulacao:  # Permite cancelar
                        return
                    
                    time.sleep(tempo_percurso / passos)
                    self.distancia_acumulada += self.distancia_metros / passos
                    
                    # Varia satélites e PDOP levemente
                    if random.random() < 0.2:
                        self.num_satelites = max(5, min(12, self.num_satelites + random.choice([-1, 0, 1])))
                        self.pdop_atual = max(1.5, min(4.0, self.pdop_atual + random.uniform(-0.3, 0.3)))
                
                # Chegou na distância - aciona servo
                self._log(f"SIMULAÇÃO: Tubo {tubo + 1}/20 lançado")
                nova_lat = self.ultima_posicao[0] + (tubo * 0.0001)
                nova_lon = self.ultima_posicao[1] + (tubo * 0.0001)
                nova_posicao = (nova_lat, nova_lon)
                
                self._gravar_coordenada(nova_posicao)
                self.servo_control.mover_operacao(posicao_alternada)
                posicao_alternada = not posicao_alternada
                
                self.ultima_posicao = nova_posicao
                self.distancia_acumulada = 0
            
            # Finaliza voo
            time.sleep(2)
            self._log("SIMULAÇÃO: Finalizando voo")
            self._finalizar_voo()
            
            # Desativa modo simulação
            self.modo_simulacao = False
            
        except Exception as e:
            self._log(f"Erro na simulação: {e}", "error")
            self.modo_simulacao = False
            self.ciclo_atual = 0
            self.estado_sistema = "AGUARDANDO_SATELITES"

    def get_gps_settings(self):
        return {
            'frequency_hz': self._frequencia_gps_hz,
            'available_frequencies': self._frequencias_disponiveis,
        }

    def set_gps_frequency(self, hz):
        hz = max(1, min(10, int(hz)))
        if hz not in self._frequencias_disponiveis:
            self._logger.warning('Frequência %s Hz não é suportada; usando mais próxima', hz)
        self._frequencia_gps_hz = hz
        self._config_manager.set('gps.frequency_hz', hz)
        self._config_manager.save()
        self._reconfigurar_gps()
        return hz

    def _reconfigurar_gps(self):
        try:
            if not self._gps_serial or not self._gps_serial.is_open:
                self._logger.info('Porta GPS não está aberta; configuração aplicada apenas no arquivo.')
                return
            # Exemplo de envio para módulos baseados em UBX
            self._logger.info('Atualizando GPS para %s Hz', self._frequencia_gps_hz)
            # TODO: enviar comando específico do módulo GPS. Placeholder:
            # self._gps_serial.write(b'...')
        except Exception as exc:
            self._logger.exception('Falha ao reconfigurar GPS: %s', exc)

