from flask import Flask, request, jsonify
import os
import json
import logging
from functools import lru_cache
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- Configuração de logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID', '1EpGuRD02oPPJOT1O6L08aqWWZuD25ZmkV9jD6rUoeAg')
RANGE_NAME = 'carteirinhas_ok!A2:D'

# --- Inicialização do serviço do Sheets ---
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

# --- Helpers ---
def normalize_matricula(raw):
    if raw is None:
        return None
    try:
        cleaned = str(raw).strip().replace(',', '.')
        intval = int(float(cleaned))
        return str(intval)
    except (ValueError, TypeError):
        return None

@lru_cache(maxsize=1)
def fetch_all_rows():
    try:
        sheet = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_NAME
        ).execute()
        rows = sheet.get('values', [])
        logger.debug('📄 Linhas obtidas da planilha: %d', len(rows))
        return rows
    except HttpError as e:
        logger.error('❗ Erro ao acessar a planilha: %s', e)
        raise
    except Exception:
        logger.exception('❗ Erro inesperado ao buscar dados da planilha')
        raise

def lookup_matricula_multiple(matricula):
    rows = fetch_all_rows()
    matches = []
    for row in rows:
        if not row:
            continue
        matricula_planilha = str(row[0]).strip()
        if matricula_planilha == matricula:
            visitante = row[1] if len(row) > 1 and row[1].strip() else 'Desconhecido'
            situacao = row[2] if len(row) > 2 and row[2].strip() else 'Indefinida'
            motivo = row[3] if len(row) > 3 and row[3].strip() else 'Nenhum motivo informado'
            matches.append({
                'visitante': visitante,
                'situacao': situacao,
                'motivo': motivo
            })
    return matches

# --- Rotas ---
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

        logger.debug('📄 Payload recebido: %s', json.dumps(data, ensure_ascii=False))
        raw_matricula = data.get('queryResult', {}).get('parameters', {}).get('matricula')
        matricula = normalize_matricula(raw_matricula)
        if not matricula:
            logger.warning('⚠️ Matrícula inválida ou ausente: %s', raw_matricula)
            return jsonify({'fulfillmentText': '⚠️ Matrícula inválida ou não informada.'}), 400

        logger.info('📌 Matrícula normalizada: %s', matricula)

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
            partes.append(
                f"{idx}. 👤 Visitante: {r['visitante']} | 📌 Situação: {r['situacao']} | 📄 Motivo: {r['motivo']}"
            )
        resposta = "Registros encontrados:\n" + "\n".join(partes)
        logger.info('✅ Matrícula %s teve %d correspondência(s)', matricula, len(resultados))
        return jsonify({'fulfillmentText': resposta}), 200

    except Exception:
        logger.exception('❗ Erro não esperado no webhook')
        return jsonify({'fulfillmentText': '❌ Erro interno.'}), 500

# --- Entry point ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info('🚀 Iniciando servidor na porta %d', port)
    app.run(host='0.0.0.0', port=port)
