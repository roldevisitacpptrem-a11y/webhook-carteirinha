from flask import Flask, request, jsonify
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# 🔐 Configurações do Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SPREADSHEET_ID = '1EpGuRD02oPPJOT1O6L08aqWWZuD25ZmkV9jD6rUoeAg'
RANGE_NAME = 'carteirinhas_ok!A:D'  # Lê todas as colunas

# 📂 Carrega as credenciais da variável de ambiente
credentials_info = json.loads(os.environ['GOOGLE_APPLICATION_CREDENTIALS_JSON'])
credentials = service_account.Credentials.from_service_account_info(
    credentials_info, scopes=SCOPES
)

# Conecta ao serviço da API
service = build('sheets', 'v4', credentials=credentials)

@app.route('/', methods=['GET'])
def home():
    return '✅ API do Rol de Visitas funcionando!'

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    parameters = req.get('queryResult', {}).get('parameters', {})
    matricula = parameters.get('matricula')

    if not matricula:
        return jsonify({'fulfillmentText': '⚠️ Matrícula não informada. Envie apenas a matrícula do preso (ex: 12345).'})

    try:
        matricula = int(matricula)
    except ValueError:
        return jsonify({'fulfillmentText': '⚠️ Matrícula inválida. Envie apenas números.'})

    try:
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        values = result.get('values', [])

        resposta = '❌ Matrícula não encontrada. Verifique se digitou corretamente.'

        for row in values:
            try:
                valor_planilha = int(row[0])
            except (ValueError, IndexError):
                continue  # pula se a primeira célula não for um número

            if valor_planilha == matricula:
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

    except Exception as e:
        resposta = f'❌ Erro ao acessar a planilha: {str(e)}'

    return jsonify({'fulfillmentText': resposta})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
