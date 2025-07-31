import os
import json
from flask import Flask, request, jsonify
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# Carregar credenciais do JSON da variável de ambiente
service_account_info = json.loads(os.environ['GOOGLE_CREDENTIALS_JSON'])

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
credentials = service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)

# ID da planilha e range
SPREADSHEET_ID = 'SEU_ID_DA_PLANILHA'
RANGE_NAME = 'Página1!A:D'  # ajuste conforme necessário

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True, force=True)
    parametros = req.get("queryResult").get("parameters")
    matricula = parametros.get("matricula")

    service = build('sheets', 'v4', credentials=credentials)
    sheet = service.spreadsheets()

    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
    values = result.get('values', [])

    resposta = "Matrícula não encontrada."
    for row in values:
        if row[0] == str(matricula):
            resposta = f"Situação: {row[1]}, Nome visitante: {row[2]}, Válida até: {row[3]}"
            break

    return jsonify({"fulfillmentText": resposta})

if __name__ == '__main__':
    app.run()
