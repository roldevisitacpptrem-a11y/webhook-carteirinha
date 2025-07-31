from flask import Flask, request, jsonify
import os
import json
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID', '1EpGuRD02oPPJOT1O6L08aqWWZuD25ZmkV9jD6rUoeAg')
RANGE_NAME = 'carteirinhas_ok!A2:D'

try:
    credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
    if not credentials_json:
        logger.error('❌ Credenciais não encontradas')
        raise ValueError('Credenciais do Google não configuradas')
    logger.info('🔑 Credenciais: %s...', credentials_json[:50])
    credentials_info = json.loads(credentials_json)
    credentials = service_account.Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
    service = build('sheets', 'v4', credentials=credentials)
    logger.info('✅ Conexão com Google Sheets estabelecida')
except Exception as e:
    logger.error('❗ Erro na conexão: %s', e)
    raise

@app.route('/', methods=['GET'])
def home():
    logger.info('🏠 Endpoint raiz')
    return '✅ API do Rol de Visitas funcionando!'

@app.route('/webhook', methods=['POST'])
def webhook():
    logger.info('📥 Requisição recebida')
    try:
        data = request.get_json(silent=True)
        if not data:
            logger.warning('⚠️ JSON inválido')
            return jsonify({'fulfillmentText': '⚠️ Requisição inválida: JSON não fornecido.'}), 400

        logger.info('📄 JSON: %s', json.dumps(data, ensure_ascii=False))
        matricula = data.get('queryResult', {}).get('parameters', {}).get('matricula')
        if not matricula:
            logger.warning('⚠️ Matrícula não informada')
            return jsonify({'fulfillmentText': '⚠️ Matrícula não informada.'}), 400

        matricula = str(matricula).strip()
        logger.info('📌 Matrícula: %s', matricula)

        try:
            result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
            rows = result.get('values', [])
            logger.info('📄 Linhas: %s', rows)
            if not rows:
                logger.warning('⚠️ Planilha vazia')
                return jsonify({'fulfillmentText': '❌ Planilha sem dados.'}), 404
        except HttpError as e:
            logger.error('❗ Erro na planilha: %s', e)
            return jsonify({'fulfillmentText': f'❌ Erro na planilha: {e}'}), 500

        for row in rows:
            if not row or len(row) < 1:
                logger.debug('Linha vazia ignorada')
                continue
            matricula_planilha = str(row[0]).strip()
            logger.info('🔍 Comparando: %s == %s', matricula_planilha, matricula)
            if matricula_planilha == matricula:
                visitante = row[1] if len(row) > 1 else 'Desconhecido'
                situacao = row[2] if len(row) > 2 else 'Indefinida'
                motivo = row[3] if len(row) > 3 else 'Nenhum motivo informado'
                resposta = f'👤 Visitante: {visitante}\n📌 Situação: {situacao}\n📄 Motivo: {motivo}'
                logger.info('✅ Encontrada: %s', resposta)
                return jsonify({'fulfillmentText': resposta})

        logger.warning('❌ Matrícula %s não encontrada', matricula)
        return jsonify({'fulfillmentText': '❌ Matrícula não encontrada.'}), 404

    except Exception as e:
        logger.error('❗ Erro: %s', e, exc_info=True)
        return jsonify({'fulfillmentText': f'❌ Erro interno: {e}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info('🚀 Servidor na porta %d', port)
    app.run(host='0.0.0.0', port=port)