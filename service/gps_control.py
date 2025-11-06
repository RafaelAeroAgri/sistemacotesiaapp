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
import serial
import pynmea2
import threading
from datetime import datetime
import pytz
import simplekml
import shutil


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
        self.numero_voo = 1
        self.pasta_voo_atual = ""
        self.pasta_backup = os.path.join(os.path.expanduser("~"), "cotesia_backup")
        os.makedirs(self.pasta_backup, exist_ok=True)
        
        # Estatísticas
        self.velocidades_registradas = []
        self.tempo_inicio_voo = None
        self.tempo_fim_voo = None
        self.data_inicio_voo = None
        
        # Thread
        self.thread_gps = None
        self.rodando = False
        
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
            'finalizado': self.finalizado
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
                        self.data_inicio_voo = datetime.now(pytz.timezone('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M:%S')
                
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
        """Cria pasta para o voo atual"""
        try:
            # Descobre próximo número de voo
            voos_existentes = glob.glob(os.path.join(self.pasta_backup, "VOO_*"))
            if voos_existentes:
                numeros = [int(v.split('_')[-1]) for v in voos_existentes if v.split('_')[-1].isdigit()]
                self.numero_voo = max(numeros) + 1 if numeros else 1
            
            self.pasta_voo_atual = os.path.join(self.pasta_backup, f"VOO_{self.numero_voo}")
            os.makedirs(self.pasta_voo_atual, exist_ok=True)
            
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
            arquivo = os.path.join(self.pasta_voo_atual, f"VOO{self.numero_voo:02d}.txt")
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
        
        self.estado_sistema = "FINALIZADO"
        self._log("✅ Voo finalizado com sucesso")
    
    def _gerar_kml(self):
        """Gera arquivos KML do percurso e pontos"""
        if not self.pasta_voo_atual:
            return
        
        try:
            arquivo_txt = os.path.join(self.pasta_voo_atual, f"VOO{self.numero_voo:02d}.txt")
            
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
            arquivo_percurso = os.path.join(self.pasta_voo_atual, f"PERCURSO{self.numero_voo:02d}.kml")
            kml_percurso.save(arquivo_percurso)
            
            # KML dos pontos
            kml_pontos = simplekml.Kml()
            for coord in coordenadas:
                pnt = kml_pontos.newpoint(name="")
                pnt.coords = [coord]
                pnt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png'
            arquivo_pontos = os.path.join(self.pasta_voo_atual, f"PONTOS{self.numero_voo:02d}.kml")
            kml_pontos.save(arquivo_pontos)
            
            self._log(f"Arquivos KML gerados com {len(coordenadas)} pontos")
        except Exception as e:
            self._log(f"Erro ao gerar KML: {e}", "error")
    
    def _gerar_relatorio(self):
        """Gera relatório do voo"""
        if not self.pasta_voo_atual:
            return
        
        try:
            arquivo = os.path.join(self.pasta_voo_atual, f"DADOS{self.numero_voo:02d}.txt")
            
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
        except Exception as e:
            self._log(f"Erro ao gerar relatório: {e}", "error")

