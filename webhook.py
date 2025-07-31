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
    logger.info('🔑 Credenciais carregadas com sucesso')
    credentials_info = json.loads(credentials_json)
    credentials = service_account.Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
    service = build('sheets', 'v4', credentials=credentials)
    logger.info('✅ Conexão com Google Sheets estabelecida')
except Exception as e:
    logger.error('❗ Erro ao conectar com Google Sheets: %s', e)
    raise

@app.route('/', methods=['GET'])
def home():
    return '✅ API do Rol de Visitas funcionando!'

@app.route('/webhook', methods=['POST'])
def webhook():
    logger.info('📥 Requisição recebida')
    try:
        data = request.get_json(silent=True)
        if not data:
            logger.warning('⚠️ JSON inválido ou não fornecido')
            return jsonify({'fulfillmentText': '⚠️ Requisição inválida: JSON não fornecido.'}), 200

        logger.info('📄 JSON recebido: %s', json.dumps(data, ensure_ascii=False))
        matricula = data.get('queryResult', {}).get('parameters', {}).get('matricula')

        if not matricula:
            logger.warning('⚠️ Matrícula não informada no parâmetro')
            return jsonify({'fulfillmentText': '⚠️ Matrícula não informada.'}), 200

        # ✅ Normaliza matrícula (corrige float ou int)
        matricula = str(int(float(matricula))).strip()
        logger.info('📌 Matrícula normalizada: %s', matricula)

        # Consulta a planilha
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_NAME
        ).execute()

        rows = result.get('values', [])
        logger.info('📄 Total de linhas lidas: %d', len(rows))

        for row in rows:
            if not row or len(row) < 1:
                continue

            matricula_planilha = str(row[0]).strip()
            logger.info('🔍 Comparando %s == %s', matricula_planilha, matricula)

            if matricula_planilha == matricula:
                visitante = row[1] if len(row) > 1 else 'Desconhecido'
                situacao = row[2] if len(row) > 2 else 'Indefinida'
                motivo = row[3] if len(row) > 3 else 'Nenhum motivo informado'
                resposta = f'👤 Visitante: {visitante}\n📌 Situação: {situacao}\n📄 Motivo: {motivo}'
                logger.info('✅ Matrícula encontrada. Enviando resposta.')
                return jsonify({'fulfillmentText': resposta}), 200

        # ❌ Se nenhuma linha bateu com a matrícula:
        resposta_nao_encontrada = '❌ Nenhuma informação encontrada para esta matrícula.'
        logger.warning(resposta_nao_encontrada)
        return jsonify({'fulfillmentText': resposta_nao_encontrada}), 200

    except Exception as e:
        logger.error('❗ Erro no processamento do webhook: %s', e, exc_info=True)
        return jsonify({'fulfillmentText': '❌ Erro interno ao consultar a matrícula.'}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info('🚀 Servidor rodando na porta %d', port)
    app.run(host='0.0.0.0', port=port)
