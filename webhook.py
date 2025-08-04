from flask import Flask, request, jsonify
import os
import json
import logging
import time
import threading
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- Configuração de logging ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SPREADSHEET_ID = '1EpGuRD02oPPJOT1O6L08aqWWZuD25ZmkV9jD6rUoeAg'
RANGE_NAME = 'carteirinhas!A2:D100000'

def init_sheets_service():
    credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
    if not credentials_json:
        logger.error('❌ Credenciais do Google não configuradas')
        raise RuntimeError('Credenciais do Google não configuradas')

    try:
        credentials_info = json.loads(credentials_json)
        credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=SCOPES
        )
        service = build('sheets', 'v4', credentials=credentials, cache_discovery=False)
        logger.info('✅ Conexão com Google Sheets estabelecida')
        return service
    except json.JSONDecodeError as e:
        logger.error('❗ JSON de credenciais inválido: %s', e)
        raise RuntimeError('Credenciais malformadas') from e
    except Exception:
        logger.exception('❗ Falha ao inicializar a API do Sheets')
        raise RuntimeError('Erro ao conectar com Google Sheets')

service = init_sheets_service()

_cache = {'rows': None, 'fetched_at': 0}
CACHE_TTL = 30  # segundos

def fetch_all_rows(force_refresh=False):
    now = time.time()
    if force_refresh or _cache['rows'] is None or now - _cache['fetched_at'] > CACHE_TTL:
        try:
            sheet = service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID,
                range=RANGE_NAME
            ).execute()
            _cache['rows'] = sheet.get('values', [])
            _cache['fetched_at'] = now
            logger.debug('📄 Cache atualizado: %d linhas', len(_cache['rows']))
        except HttpError as e:
            logger.error('❗ Erro ao acessar a planilha: %s', e)
            raise
        except Exception:
            logger.exception('❗ Erro inesperado ao buscar dados da planilha')
            raise
    else:
        logger.debug('♻ Usando cache da planilha (há %.1f segundos)', now - _cache['fetched_at'])
    return _cache['rows']

def clear_cache():
    _cache['rows'] = None
    _cache['fetched_at'] = 0
    logger.info('🧹 Cache manual limpo')

def normalize_matricula(raw):
    if raw is None:
        return None
    try:
        cleaned = str(raw).strip().replace(',', '.')
        intval = int(float(cleaned))
        return str(intval)
    except (ValueError, TypeError):
        return None

def clean_key(s):
    return ''.join(c for c in str(s).strip() if c.isprintable())

def sanitize_situacao(raw_situacao):
    if not raw_situacao:
        return 'Indefinida'
    text = str(raw_situacao).strip().lower()
    if 'irregular' in text:
        return 'Irregular'
    return str(raw_situacao).strip()

def clean_motivo(text):
    if not text:
        return ''
    text = str(text)
    text = text.replace('\n', ' ').replace('\r', ' ')
    text = ' '.join(text.split())
    return text

def lookup_matricula_multiple(matricula, force_refresh=False):
    rows = fetch_all_rows(force_refresh=force_refresh)
    matches = []
    for row in rows:
        if not row:
            continue
        matricula_planilha = clean_key(row[0])
        if matricula_planilha == clean_key(matricula):
            visitante = row[1] if len(row) > 1 and row[1].strip() else 'Desconhecido'
            situacao_raw = row[2] if len(row) > 2 and row[2].strip() else ''
            situacao = sanitize_situacao(situacao_raw)
            motivo_raw = row[3] if len(row) > 3 and row[3].strip() else ''
            motivo = clean_motivo(motivo_raw)
            matches.append({
                'visitante': visitante,
                'situacao': situacao,
                'motivo': motivo
            })
    return matches

def keep_alive_ping(interval=240):
    def ping_loop():
        while True:
            try:
                public_url = os.environ.get('PUBLIC_URL')
                if not public_url:
                    logger.warning('⚠️ PUBLIC_URL não está configurado; pulando keep-alive ping')
                else:
                    target = public_url if public_url.endswith('/') else public_url + '/'
                    requests.get(target, timeout=10)
                    logger.debug('🔁 Keep-alive ping enviado para %s', target)
            except Exception:
                logger.exception('❗ Falha no keep-alive ping')
            time.sleep(interval)
    thread = threading.Thread(target=ping_loop, daemon=True)
    thread.start()

keep_alive_ping()

@app.route('/', methods=['GET'])
def home():
    logger.info('🏠 Endpoint raiz acessado')
    return '✅ API do Rol de Visitas funcionando!'

@app.route('/webhook', methods=['POST'])
def webhook():
    logger.info('📥 Requisição recebida no /webhook')
    try:
        data = request.get_json(silent=True)
        if not data:
            logger.warning('⚠️ JSON inválido ou não fornecido')
            return jsonify({'fulfillmentText': '⚠️ Requisição inválida: JSON não fornecido.'}), 400

        raw_matricula = data.get('queryResult', {}).get('parameters', {}).get('matricula')
        logger.info('🔍 Matrícula bruta recebida: %r', raw_matricula)
        matricula = normalize_matricula(raw_matricula)
        logger.info('🔁 Matrícula após normalização: %r', matricula)

        if not matricula:
            logger.warning('⚠️ Matrícula inválida ou ausente: %s', raw_matricula)
            return jsonify({'fulfillmentText': '⚠️ Matrícula inválida ou não informada.'}), 400

        try:
            resultados = lookup_matricula_multiple(matricula)
        except HttpError:
            return jsonify({'fulfillmentText': '❌ Erro ao acessar a planilha. Tente novamente mais tarde.'}), 500
        except Exception:
            return jsonify({'fulfillmentText': '❌ Erro interno ao buscar dados.'}), 500

        if not resultados:
            logger.warning('❌ Matrícula %s não encontrada', matricula)
            return jsonify({'fulfillmentText': f'❌ Nenhuma informação encontrada para a matrícula {matricula}.'}), 200

        partes = []
        for idx, r in enumerate(resultados, start=1):
            if r['situacao'].lower() == 'irregular':
                motivo_final = r['motivo'] if r['motivo'] else 'Nenhum motivo informado'
            else:
                motivo_final = 'Nenhum motivo informado'
            partes.append(f"{idx}. 👤 Visitante: {r['visitante']} | 📌 Situação: {r['situacao']} | 📄 Motivo: {motivo_final}")

        resposta = "Registros encontrados:\n" + "\n".join(partes)
        logger.info('✅ Matrícula %s teve %d correspondência(s)', matricula, len(resultados))
        return jsonify({'fulfillmentText': resposta}), 200

    except Exception:
        logger.exception('❗ Erro não esperado no webhook')
        return jsonify({'fulfillmentText': '❌ Erro interno.'}), 500

@app.route('/debug_rows', methods=['GET'])
def debug_rows():
    try:
        rows = fetch_all_rows()
        sample = rows[:20]
        logger.info('Amostra das primeiras 20 linhas solicitada via /debug_rows')
        return jsonify({'sample': sample}), 200
    except Exception:
        logger.exception('Erro ao buscar linhas para debug')
        return jsonify({'error': 'Falha ao obter linhas'}), 500

@app.route('/refresh_cache', methods=['POST', 'GET'])
def refresh_cache():
    clear_cache()
    return jsonify({'status': 'cache limpo'}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info('🚀 Iniciando servidor na porta %d', port)
    app.run(host='0.0.0.0', port=port)
