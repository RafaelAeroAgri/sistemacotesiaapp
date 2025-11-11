#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor HTTP REST para o Sistema Cotesia
Expõe API para controle remoto via WiFi
"""

import sys
import os
import signal
import json
import base64
import glob
import shutil
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Importa módulos do serviço
from logger import configurar_logging
from servo_control import ServoControl
from gps_control import GPSControl


class CotesiaHTTPHandler(BaseHTTPRequestHandler):
    """Handler para requisições HTTP"""
    
    servo_control = None
    gps_control = None
    logger = None
    pasta_backup = None
    
    def do_OPTIONS(self):
        """Trata requisições OPTIONS para CORS"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        """Processa requisições GET"""
        parsed = urlparse(self.path)
        raw_path = parsed.path or '/'
        path = raw_path.rstrip('/') or '/'
        path_lower = path.lower()
        
        try:
            # PING - Teste de conectividade
            if path_lower == '/ping':
                self.send_json({'status': 'ok', 'message': 'PONG'})
            
            # STATUS - Status completo do sistema
            elif path_lower == '/status':
                status = self.gps_control.get_status()
                status.update({
                    'servos_estado': self.servo_control.get_estado(),
                    'pasta_backup': self.pasta_backup
                })
                self.send_json({'status': 'ok', 'data': status})
            
            # CONFIG - Configurações atuais
            elif path_lower == '/config':
                config = self.gps_control.get_config()
                self.send_json({'status': 'ok', 'config': config})

            # SERVO/CALIBRATION - Calibração atual
            elif path_lower == '/servo/calibration':
                if hasattr(self.servo_control, 'get_calibration'):
                    if self.logger:
                        self.logger.debug("GET /servo/calibration usando método get_calibration()")
                    calibration = self.servo_control.get_calibration()
                else:
                    calibration = getattr(self.servo_control, 'calibration', None)
                    if self.logger:
                        self.logger.warning(
                            "GET /servo/calibration: método get_calibration() ausente; retornando atributo bruto"
                            if calibration is not None else
                            "GET /servo/calibration: calibração indisponível nesta versão"
                        )
                if calibration is not None:
                    self.send_json({'status': 'ok', 'calibration': calibration})
                else:
                    self.send_json(
                        {'status': 'error', 'message': 'Função de calibração não disponível nesta versão'},
                        501
                    )
                return
            
            elif path_lower == '/servo/calibration/measure':
                if hasattr(self.servo_control, 'medir_calibracao'):
                    if self.logger:
                        self.logger.info("Executando medição automática de calibração dos servos")
                    calibration = self.servo_control.medir_calibracao()
                    self.send_json({'status': 'ok', 'calibration': calibration})
                else:
                    if self.logger:
                        self.logger.warning("Medição de calibração não suportada nesta versão")
                    self.send_json(
                        {'status': 'error', 'message': 'Medição automática não disponível nesta versão'},
                        501
                    )
                return
            
            # FLIGHTS/LIST - Lista todos os voos
            elif path == '/flights/list':
                flights = self._listar_voos()
                self.send_json({'status': 'ok', 'flights': flights})
            
            # FLIGHTS/{numero} - Dados de um voo específico
            elif path_lower.startswith('/flights/') and len(path.split('/')) == 3:
                numero = path.split('/')[-1]
                if numero.isdigit():
                    flight_data = self._obter_dados_voo(int(numero))
                    if flight_data:
                        self.send_json({'status': 'ok', 'flight': flight_data})
                    else:
                        self.send_json({'status': 'error', 'message': 'Voo não encontrado'}, 404)
                else:
                    self.send_json({'status': 'error', 'message': 'Número de voo inválido'}, 400)
            
            # ROOT - Informações da API
            elif path_lower == '/':
                self.send_json({
                    'service': 'Sistema Cotesia HTTP Server',
                    'version': '1.0.0',
                    'endpoints': {
                        'GET /ping': 'Testa conectividade',
                        'GET /status': 'Status completo do sistema',
                        'GET /config': 'Configurações atuais',
                        'POST /config': 'Atualiza configurações',
                        'POST /servo/test': 'Teste de servos',
                        'POST /servo/reset': 'Reset servos',
                        'POST /servo/angle': 'Ajuste manual de servo',
                        'GET /servo/calibration': 'Obtém calibração',
                        'POST /servo/calibration': 'Atualiza calibração',
                        'POST /system/boot': 'Inicializa GPIO',
                        'POST /system/reset': 'Reset completo',
                        'POST /flight/start': 'Inicia voo',
                        'POST /flight/stop': 'Para voo',
                        'GET /flights/list': 'Lista voos',
                        'GET /flights/{numero}': 'Dados do voo',
                        'DELETE /flights/{numero}': 'Apaga voo'
                    }
                })
            
            else:
                self.send_json({'status': 'error', 'message': 'Endpoint não encontrado'}, 404)
        
        except Exception as e:
            if self.logger:
                self.logger.error(f"Erro no GET: {e}", exc_info=True)
            self.send_json({'status': 'error', 'message': str(e)}, 500)
    
    def do_POST(self):
        """Processa requisições POST"""
        parsed = urlparse(self.path)
        raw_path = parsed.path or '/'
        path = raw_path.rstrip('/') or '/'
        path_lower = path.lower()
        
        try:
            # Lê body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
            data = json.loads(body) if body else {}
            
            # SERVO/TEST - Teste de servos
            if path_lower == '/servo/test':
                success = self.servo_control.teste()
                if success:
                    self.send_json({'status': 'ok', 'message': 'Teste executado'})
                else:
                    self.send_json({'status': 'error', 'message': 'Falha no teste'}, 500)
            
            # SERVO/RESET - Reset servos
            elif path_lower == '/servo/reset':
                success = self.servo_control.reset()
                if success:
                    self.send_json({'status': 'ok', 'message': 'Servos resetados'})
                else:
                    self.send_json({'status': 'error', 'message': 'Falha no reset'}, 500)
            
            # SERVO/ANGLE - Ajuste manual de servo
            elif path_lower == '/servo/angle':
                servo = data.get('servo')
                valor = data.get('value')
                
                if valor is None and 'degrees' in data:
                    try:
                        graus = float(data.get('degrees'))
                        valor = (graus / 90.0) - 1.0
                    except (TypeError, ValueError):
                        valor = None
                
                try:
                    servo = int(servo)
                except (TypeError, ValueError):
                    servo = None
                
                if servo in (1, 2) and valor is not None:
                    success = self.servo_control.ajustar_servo(servo, valor)
                    if success:
                        estado = self.servo_control.get_estado()
                        self.send_json({
                            'status': 'ok',
                            'message': f'Servo {servo} ajustado',
                            'servo_estado': estado
                        })
                    else:
                        self.send_json({'status': 'error', 'message': 'Falha ao ajustar servo'}, 500)
                else:
                    self.send_json(
                        {'status': 'error', 'message': 'Informe servo (1 ou 2) e value'}, 400
                    )

            # SERVO/CALIBRATION - Atualiza calibração
            elif path_lower == '/servo/calibration':
                if hasattr(self.servo_control, 'set_calibration'):
                    if self.logger:
                        self.logger.debug("POST /servo/calibration usando set_calibration()")
                    success = self.servo_control.set_calibration(data)
                else:
                    success = False
                    if self.logger:
                        self.logger.warning("POST /servo/calibration: método set_calibration() ausente nesta versão")
                if success:
                    self.send_json({'status': 'ok', 'message': 'Calibração atualizada'})
                else:
                    self.send_json(
                        {'status': 'error', 'message': 'Calibração não suportada nesta versão'},
                        501
                    )
            
            elif path_lower == '/servo/calibration/detect':
                if hasattr(self.servo_control, 'detectar_limites'):
                    if self.logger:
                        self.logger.debug("POST /servo/calibration/detect: executando detecção de limites")
                    limites = self.servo_control.detectar_limites()
                    if limites:
                        self.send_json({'status': 'ok', 'calibration': limites})
                    else:
                        self.send_json(
                            {'status': 'error', 'message': 'Falha na detecção de limites'},
                            500
                        )
                else:
                    if self.logger:
                        self.logger.warning("POST /servo/calibration/detect indisponível nesta versão")
                    self.send_json(
                        {'status': 'error', 'message': 'Detecção automática não disponível nesta versão'},
                        501
                    )
            
            elif path_lower == '/servo/calibration/measure':
                if hasattr(self.servo_control, 'medir_calibracao'):
                    if self.logger:
                        self.logger.info("POST /servo/calibration/measure: executando medição")
                    calibration = self.servo_control.medir_calibracao()
                    self.send_json({'status': 'ok', 'calibration': calibration})
                else:
                    if self.logger:
                        self.logger.warning("POST /servo/calibration/measure: não suportado nesta versão")
                    self.send_json(
                        {'status': 'error', 'message': 'Medição automática não disponível nesta versão'},
                        501
                    )
            
            # SYSTEM/BOOT - Inicializa GPIO
            elif path_lower == '/system/boot':
                if self.servo_control.inicializado:
                    self.send_json({'status': 'ok', 'message': 'Sistema já inicializado'})
                else:
                    success = self.servo_control.inicializar_gpio()
                    if success:
                        self.send_json({'status': 'ok', 'message': 'Sistema inicializado'})
                    else:
                        self.send_json({'status': 'error', 'message': 'Falha na inicialização'}, 500)
            
            # SYSTEM/RESET - Reset completo
            elif path_lower == '/system/reset':
                success = self.gps_control.resetar_sistema()
                if success:
                    self.send_json({'status': 'ok', 'message': 'Sistema resetado'})
                else:
                    self.send_json({'status': 'error', 'message': 'Falha no reset'}, 500)
            
            # FLIGHT/START - Inicia voo
            elif path_lower == '/flight/start':
                success = self.gps_control.iniciar_voo()
                if success:
                    self.send_json({'status': 'ok', 'message': 'Voo iniciado'})
                else:
                    self.send_json({'status': 'error', 'message': 'Não foi possível iniciar voo'}, 400)
            
            # FLIGHT/STOP - Para voo
            elif path_lower == '/flight/stop':
                success = self.gps_control.parar_voo()
                if success:
                    self.send_json({'status': 'ok', 'message': 'Voo parado'})
                else:
                    self.send_json({'status': 'error', 'message': 'Falha ao parar voo'}, 500)
            
            # FLIGHT/SIMULATE - Inicia simulação
            elif path_lower == '/flight/simulate':
                if hasattr(self.gps_control, 'iniciar_simulacao'):
                    if self.logger:
                        self.logger.debug("POST /flight/simulate chamando iniciar_simulacao()")
                    velocidade_media = data.get('velocidade_media', 12)
                    success = self.gps_control.iniciar_simulacao(velocidade_media)
                    if success:
                        self.send_json({'status': 'ok', 'message': 'Simulação iniciada'})
                    else:
                        self.send_json({'status': 'error', 'message': 'Não foi possível iniciar simulação'}, 400)
                else:
                    if self.logger:
                        self.logger.warning("POST /flight/simulate: método iniciar_simulacao() ausente nesta versão")
                    self.send_json(
                        {'status': 'error', 'message': 'Simulação não disponível nesta versão'},
                        501
                    )
            
            # CONFIG - Atualiza configurações
            elif path_lower == '/config':
                success = self.gps_control.set_config(data)
                if success:
                    self.send_json({'status': 'ok', 'message': 'Configurações atualizadas'})
                else:
                    self.send_json({'status': 'error', 'message': 'Falha ao atualizar'}, 500)
            
            else:
                self.send_json({'status': 'error', 'message': f'Endpoint não encontrado ({raw_path})'}, 404)
        
        except json.JSONDecodeError:
            self.send_json({'status': 'error', 'message': 'JSON inválido'}, 400)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Erro no POST: {e}", exc_info=True)
            self.send_json({'status': 'error', 'message': str(e)}, 500)
    
    def do_DELETE(self):
        """Processa requisições DELETE"""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/') or '/'
        
        try:
            # DELETE /flights/{numero}
            if path.startswith('/flights/') and len(path.split('/')) == 3:
                numero = path.split('/')[-1]
                if numero.isdigit():
                    success = self._apagar_voo(int(numero))
                    if success:
                        self.send_json({'status': 'ok', 'message': f'Voo {numero} apagado'})
                    else:
                        self.send_json({'status': 'error', 'message': 'Voo não encontrado'}, 404)
                else:
                    self.send_json({'status': 'error', 'message': 'Número de voo inválido'}, 400)
            else:
                self.send_json({'status': 'error', 'message': 'Endpoint não encontrado'}, 404)
        
        except Exception as e:
            if self.logger:
                self.logger.error(f"Erro no DELETE: {e}", exc_info=True)
            self.send_json({'status': 'error', 'message': str(e)}, 500)
    
    def send_json(self, data, status_code=200):
        """Envia resposta JSON"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def log_message(self, format, *args):
        """Override para usar nosso logger"""
        if self.logger:
            self.logger.info(f"{self.address_string()} - {format % args}")
    
    def _listar_voos(self):
        """Lista todos os voos salvos"""
        voos = []
        try:
            # Estrutura nova (com metadata)
            for meta in self._iterar_voos_metadata():
                voos.append(self._montar_info_voo_meta(meta))
            
            # Compatibilidade com estrutura antiga
            voos.extend(self._listar_voos_legado())
            
            voos.sort(
                key=lambda v: (
                    v.get('data_iso') or '',
                    v.get('numero') or 0
                ),
                reverse=True
            )
        except Exception as e:
            if self.logger:
                self.logger.error(f"Erro ao listar voos: {e}", exc_info=True)
        
        return voos
    
    def _obter_dados_voo(self, numero):
        """Obtém dados completos de um voo (arquivos em base64)"""
        try:
            pasta, metadata = self._buscar_voo_por_numero(numero)
            if not pasta or not os.path.exists(pasta):
                return None
            
            if metadata is None:
                metadata = {
                    'id': f"legacy-{numero}",
                    'numero': numero,
                    'legacy': True,
                    'pasta_relativa': os.path.relpath(pasta, self.pasta_backup)
                }
            
            dados = {
                'numero': numero,
                'metadata': metadata,
                'arquivos': {}
            }
            
            # Lê todos os arquivos (exceto metadata duplicada)
            for arquivo in os.listdir(pasta):
                if arquivo.lower() == 'metadata.json':
                    continue
                caminho = os.path.join(pasta, arquivo)
                if not os.path.isfile(caminho):
                    continue
                with open(caminho, 'rb') as f:
                    conteudo = f.read()
                    dados['arquivos'][arquivo] = base64.b64encode(conteudo).decode('utf-8')
            
            return dados
        
        except Exception as e:
            if self.logger:
                self.logger.error(f"Erro ao obter dados do voo: {e}")
            return None
    
    def _apagar_voo(self, numero):
        """Apaga um voo da Raspberry"""
        try:
            pasta, _ = self._buscar_voo_por_numero(numero)
            if not pasta or not os.path.exists(pasta):
                return False
            
            shutil.rmtree(pasta)
            
            if self.logger:
                self.logger.info(f"Voo {numero} apagado")
            
            return True
        
        except Exception as e:
            if self.logger:
                self.logger.error(f"Erro ao apagar voo: {e}")
            return False

    def _iterar_voos_metadata(self):
        """Itera sobre todos os arquivos de metadata da estrutura nova"""
        pattern = os.path.join(self.pasta_backup, "**", "metadata.json")
        arquivos_meta = glob.glob(pattern, recursive=True)
        for meta_file in arquivos_meta:
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    dados = json.load(f)
                dados['_path'] = os.path.dirname(meta_file)
                yield dados
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Falha ao ler metadata {meta_file}: {e}")

    def _montar_info_voo_meta(self, meta):
        """Monta dicionário de informações a partir da metadata do voo"""
        info = {
            'id': meta.get('id'),
            'numero': meta.get('numero_global') or meta.get('numero'),
            'numero_diario': meta.get('numero_diario'),
            'ano': meta.get('ano'),
            'mes': meta.get('mes'),
            'mes_nome': meta.get('mes_nome'),
            'dia': meta.get('dia'),
            'data': meta.get('data_humana'),
            'data_iso': meta.get('data_iso'),
            'tubos': meta.get('tubos', 0),
            'duracao': meta.get('duracao_humana', ''),
            'tamanho_mb': meta.get('tamanho_mb', 0),
            'pasta_relativa': meta.get('pasta_relativa'),
            'arquivos': meta.get('arquivos', {}),
        }
        return info

    def _listar_voos_legado(self):
        """Compatibilidade com estrutura antiga (sem metadata)"""
        voos = []
        pastas_voos = glob.glob(os.path.join(self.pasta_backup, "VOO_*"))
        for pasta in sorted(pastas_voos):
            if not os.path.isdir(pasta):
                continue
            try:
                numero = int(os.path.basename(pasta).split('_')[-1])
            except ValueError:
                continue

            info = {
                'id': f"legacy-{numero}",
                'numero': numero,
                'data': 'N/A',
                'data_humana': 'N/A',
                'data_iso': '',
                'tubos': 0,
                'duracao': 'N/A',
                'tamanho_mb': 0,
                'pasta_relativa': os.path.relpath(pasta, self.pasta_backup),
                'legacy': True,
            }

            # Calcula tamanho total
            tamanho_total = 0
            for arquivo in os.listdir(pasta):
                caminho = os.path.join(pasta, arquivo)
                if os.path.isfile(caminho):
                    tamanho_total += os.path.getsize(caminho)
            info['tamanho_mb'] = round(tamanho_total / 1024 / 1024, 2)

            arquivo_dados = os.path.join(pasta, f"DADOS{numero:02d}.txt")
            if os.path.exists(arquivo_dados):
                try:
                    with open(arquivo_dados, 'r', encoding='utf-8') as f:
                        conteudo = f.read()
                        for linha in conteudo.split('\n'):
                            if 'Data:' in linha:
                                info['data'] = linha.split('Data:')[1].strip()
                            elif 'Tubos lançados:' in linha:
                                info['tubos'] = int(linha.split(':')[1].strip())
                            elif 'Duração:' in linha:
                                info['duracao'] = linha.split('Duração:')[1].strip()
                except Exception:
                    pass

            info['data_humana'] = info['data']
            try:
                parsed = datetime.strptime(info['data'], '%d/%m/%Y %H:%M:%S')
                info['data_iso'] = parsed.isoformat()
                info.setdefault('ano', parsed.year)
                info.setdefault('mes', parsed.month)
                info.setdefault('dia', parsed.day)
            except Exception:
                info['data_iso'] = ''

            voos.append(info)
        return voos

    def _buscar_voo_por_numero(self, numero):
        """Localiza pasta e metadata de um voo pelo número global"""
        try:
            for meta in self._iterar_voos_metadata():
                meta_num = meta.get('numero_global') or meta.get('numero')
                if meta_num and int(meta_num) == int(numero):
                    caminho = meta['_path']
                    meta_copia = {k: v for k, v in meta.items() if k != '_path'}
                    return caminho, meta_copia
        except Exception as e:
            if self.logger:
                self.logger.error(f"Erro ao buscar metadata do voo {numero}: {e}")

        # Fallback para estrutura antiga
        pasta_legado = os.path.join(self.pasta_backup, f"VOO_{numero}")
        if os.path.exists(pasta_legado):
            return pasta_legado, None
        return None, None


def main():
    """Função principal"""
    print("Sistema Cotesia HTTP Server")
    print("=" * 60)
    
    # Inicializa logger
    logger = configurar_logging()
    
    logger.info("=" * 60)
    logger.info("Sistema Cotesia HTTP Server iniciando...")
    logger.info("=" * 60)
    
    # Pasta de backup
    pasta_backup = os.path.join(os.path.expanduser("~"), "cotesia_backup")
    os.makedirs(pasta_backup, exist_ok=True)
    logger.info(f"Pasta de backup: {pasta_backup}")
    
    # Inicializa controle de servos
    servo_control = ServoControl(logger=logger)
    # Inicializa GPIO automaticamente sem mover servos
    # Inicializa GPIO de forma silenciosa (sem movimentar servos).
    if hasattr(servo_control, "inicializar_gpio_silencioso"):
        servo_control.inicializar_gpio_silencioso()
    else:
        try:
            servo_control.inicializar_gpio(calibrar=False)
        except TypeError:
            servo_control.inicializar_gpio()
    
    # Inicializa controle de GPS
    config = {
        'distancia_metros': 25,
        'tempo_parada': 10,
        'velocidade_operacao': 5.0,
        'precisao_minima_satelites': 3,
        'pdop_maximo': 6.0,
        'first_movement_threshold': 5.0,
        'velocidade_parada': 1.5
    }
    gps_control = GPSControl(servo_control, logger=logger, config=config)
    
    # Inicia GPS
    gps_control.iniciar()
    
    # Configura handler
    CotesiaHTTPHandler.servo_control = servo_control
    CotesiaHTTPHandler.gps_control = gps_control
    CotesiaHTTPHandler.logger = logger
    CotesiaHTTPHandler.pasta_backup = pasta_backup
    
    # Inicia servidor HTTP
    host = '0.0.0.0'  # Escuta em todas as interfaces
    port = 8080
    
    server = HTTPServer((host, port), CotesiaHTTPHandler)
    
    logger.info(f"Servidor HTTP rodando em {host}:{port}")
    logger.info("API REST disponível para controle remoto via WiFi")
    
    # Handler de sinais
    def signal_handler(signum, frame):
        logger.info("Encerrando servidor...")
        gps_control.parar()
        servo_control.limpar()
        server.shutdown()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Servidor interrompido")
    finally:
        gps_control.parar()
        servo_control.limpar()


if __name__ == "__main__":
    main()

