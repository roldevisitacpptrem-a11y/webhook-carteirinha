from flask import Flask, request, jsonify
import os
import json
import logging
import time
import threading
import requests
import re
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- Logging ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Config Google Sheets ---
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SPREADSHEET_ID = '1EpGuRD02oPPJOT1O6L08aqWWZuD25ZmkV9jD6rUoeAg'
RANGE_NAME = 'carteirinhas_ok!A2:D100000'

# --- Serviço Sheets ---
def get_sheets_service():
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
        return build('sheets', 'v4', credentials=credentials, cache_discovery=False)
    except Exception as e:
        logger.exception('❗ Falha ao inicializar a API do Sheets')
        raise RuntimeError('Erro ao conectar com Google Sheets') from e

# --- Cache ---
_cache = {'dict': None, 'fetched_at': 0}
CACHE_TTL = 30

def clear_cache():
    _cache['dict'] = None
    _cache['fetched_at'] = 0
    logger.info('🧹 Cache manual limpo')

# --- Normalização ---
def normalize_matricula(raw):
    if not raw:
        return None
    cleaned = str(raw).strip()
    cleaned = re.sub(r'[\u200B\u200C\u200D\u200E\u200F\u202A-\u202E\u2060\uFEFF]', '', cleaned)
    cleaned = re.sub(r'[\s\.\-]', '', cleaned)
    # Remove zeros à esquerda
    cleaned = cleaned.lstrip('0')
    return cleaned or '0'

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
    text = str(text).replace('\n', ' ').replace('\r', ' ')
    return ' '.join(text.split())

# --- Fetch e lookup ---
def fetch_all_rows(force_refresh=False):
    now = time.time()
    if force_refresh or _cache['dict'] is None or now - _cache['fetched_at'] > CACHE_TTL:
        try:
            service = get_sheets_service()
            sheet = service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID,
                range=RANGE_NAME
            ).execute()
            rows = sheet.get('values', [])
            matr_dict = {}
            for row in rows:
                if not row or not row[0].strip():
                    continue
                matricula = normalize_matricula(row[0])
                visitante = row[1].strip() if len(row) > 1 and row[1].strip() else 'Desconhecido'
                situacao = sanitize_situacao(row[2] if len(row) > 2 else '')
                motivo = clean_motivo(row[3] if len(row) > 3 else '')
                registro = {'visitante': visitante, 'situacao': situacao, 'motivo': motivo}

                # Evita duplicatas
                if matricula not in matr_dict:
                    matr_dict[matricula] = []
                if registro not in matr_dict[matricula]:
                    matr_dict[matricula].append(registro)

            _cache['dict'] = matr_dict
            _cache['fetched_at'] = now
            logger.debug('📄 Cache atualizado: %d matrículas únicas', len(matr_dict))
        except HttpError as e:
            logger.error('❗ Erro ao acessar a planilha: %s', e)
            raise
        except Exception:
            logger.exception('❗ Erro inesperado ao buscar dados da planilha')
            raise
    else:
        logger.debug('♻ Usando cache da planilha (há %.1f segundos)', now - _cache['fetched_at'])
    return _cache['dict']

def lookup_matricula(matricula, force_refresh=False):
    matr_dict = fetch_all_rows(force_refresh=force_refresh)
    matricula_clean = normalize_matricula(matricula)
    return matr_dict.get(matricula_clean, [])

# --- Keep-alive ---
def keep_alive_ping(interval=240):
    def ping_loop():
        while True:
            try:
                public_url = os.environ.get('PUBLIC_URL')
                if public_url:
                    target = public_url if public_url.endswith('/') else public_url + '/'
                    requests.get(target, timeout=10)
                    logger.debug('🔁 Keep-alive ping enviado para %s', target)
            except Exception:
                logger.exception('❗ Falha no keep-alive ping')
            time.sleep(interval)
    threading.Thread(target=ping_loop, daemon=True).start()

keep_alive_ping()

# --- Endpoints ---
@app.route('/', methods=['GET'])
def home():
    return '✅ API do Rol de Visitas funcionando!'

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'fulfillmentText': '⚠️ Requisição inválida: JSON não fornecido.'}), 400

        raw_matricula = data.get('queryResult', {}).get('parameters', {}).get('matricula')
        matricula = normalize_matricula(raw_matricula)
        logger.debug('🔍 Matrícula recebida: "%s", normalizada: "%s"', raw_matricula, matricula)

        if not matricula:
            return jsonify({'fulfillmentText': '⚠️ Matrícula inválida ou não informada.'}), 400

        resultados = lookup_matricula(matricula)
        logger.debug('🔍 Resultados encontrados: %s', resultados)

        if not resultados:
            return jsonify({'fulfillmentText': f'❌ Nenhuma informação encontrada para a matrícula {matricula}.'}), 200

        partes = []
        for idx, r in enumerate(resultados, start=1):
            motivo_final = r['motivo'] if r['motivo'] else 'Nenhum motivo informado'
            partes.append(f"{idx}. 👤 {r['visitante']} | 📌 {r['situacao']} | 📄 {motivo_final}")

        resposta = "📋 *Registros encontrados:*\n" + "\n".join(partes)
        return jsonify({'fulfillmentText': resposta}), 200

    except Exception:
        logger.exception('❗ Erro no webhook')
        return jsonify({'fulfillmentText': '❌ Erro interno.'}), 500

@app.route('/debug_rows', methods=['GET'])
def debug_rows():
    try:
        matr_dict = fetch_all_rows()
        sample = {k: matr_dict[k] for k in list(matr_dict.keys())[:20]}
        return jsonify({'sample': sample}), 200
    except Exception:
        return jsonify({'error': 'Falha ao obter linhas'}), 500

@app.route('/refresh_cache', methods=['POST', 'GET'])
def refresh_cache():
    clear_cache()
    return jsonify({'status': 'cache limpo'}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
