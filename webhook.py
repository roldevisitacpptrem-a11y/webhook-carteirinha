from flask import Flask, request, jsonify
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# Configuração da API do Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = '1EpGuRD02oPPJOT1O6L08aqWWZuD25ZmkV9jD6rUoeAg'
RANGE_NAME = 'carteirinhas_ok!A3:D'  # Começa na A3 (dados), pula cabeçalho

# Carrega as credenciais do JSON a partir da variável de ambiente
credentials_info = json.loads(os.environ['GOOGLE_APPLICATION_CREDENTIALS_JSON'])
credentials = service_account.Credentials.from_service_account_info(
    credentials_info, scopes=SCOPES
)

service = build('sheets', 'v4', credentials=credentials)

@app.route('/', methods=['GET'])
def home():
    return '✅ API do Rol de Visitas funcionando!'

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    parameters = req['queryResult']['parameters']
    matricula = parameters.get('matricula')

    if not matricula:
        return jsonify({'fulfillmentText': '⚠️ Matrícula não informada. Por favor, envie apenas a matrícula do preso (ex: 12345).'})

    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
    values = result.get('values', [])

    resposta = '❌ Matrícula não encontrada. Verifique se digitou corretamente.'

    for row in values:
        if len(row) >= 1 and str(row[0]).strip() == str(matricula).strip():
            nome_visitante = row[1] if len(row) > 1 else 'Desconhecido'
            situacao = row[2] if len(row) > 2 else 'Indefinida'
            motivo = row[3] if len(row) > 3 else 'Nenhum motivo informado'

            resposta = (
                f'🔎 *Carteirinha encontrada:*\n'
                f'👤 Visitante: {nome_visitante}\n'
                f'📌 Situação: {situacao}\n'
                f'📄 Motivo: {motivo}'
            )
            break

    return jsonify({'fulfillmentText': resposta})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
