from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os
import pyodbc

app = FastAPI()

# CORS configuración
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://192.168.0.9:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración SQL Server
server = 'DESKTOP-SO7UMP1\\SQLEXPRESS'
database = 'Voltaren'
conn_str = (
    f'DRIVER={{ODBC Driver 17 for SQL Server}};'
    f'SERVER={server};'
    f'DATABASE={database};'
    'Trusted_Connection=yes;'
    'TrustServerCertificate=yes;'
)
conn = pyodbc.connect(conn_str)
cursor = conn.cursor()

# Google Drive configuración
SERVICE_ACCOUNT_FILE = 'credenciales.json'
SCOPES = ['https://www.googleapis.com/auth/drive']
FOLDER_ID = '1dQ6cDyZPwWQnsdsHrAnsSRvzjEtPRD40'

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
drive_service = build('drive', 'v3', credentials=credentials)

# Carpeta temporal local
os.makedirs("documentos", exist_ok=True)

@app.post("/subir-pdf")
async def subir_pdf(cedula: str = Form(...), nombres: str = Form(...), file: UploadFile = None):
    try:
        if not file:
            return JSONResponse(content={"error": "No se envió el archivo PDF"}, status_code=400)

        nombre_archivo = f"{cedula}_{file.filename}"
        ruta_temp = os.path.join("documentos", nombre_archivo)

        # Guardar el archivo temporalmente
        with open(ruta_temp, "wb") as buffer:
            contenido = await file.read()
            buffer.write(contenido)

        # Subir a Google Drive
        file_metadata = {
            'name': nombre_archivo,
            'parents': [FOLDER_ID]
        }
        media = MediaFileUpload(ruta_temp, mimetype='application/pdf')
        uploaded_file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()

        file_id = uploaded_file.get('id')

        # Hacer el archivo público
        drive_service.permissions().create(
            fileId=file_id,
            body={'role': 'reader', 'type': 'anyone'}
        ).execute()

        url_drive = f"https://drive.google.com/file/d/{file_id}/view"

        # Guardar en la base de datos
        cursor.execute(
            "INSERT INTO documentos_firmados (cedula, nombres, ruta_pdf) VALUES (?, ?, ?)",
            cedula, nombres, url_drive
        )
        conn.commit()

        return {"mensaje": "Documento subido y guardado exitosamente", "url": url_drive}

    except Exception as e:
        conn.rollback()
        print(f"⚠️ Error detallado: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)
