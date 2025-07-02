from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os
import json
import psycopg2

app = FastAPI()

# CORS configuración
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://192.168.0.9:5173"],  # Cambia por la IP o dominio de tu frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración PostgreSQL usando variables de entorno
conn = psycopg2.connect(
    dbname=os.getenv("DB_NAME", "postgres"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT", "5432")
)
cursor = conn.cursor()

# Google Drive configuración desde variable de entorno
SCOPES = ['https://www.googleapis.com/auth/drive']
FOLDER_ID = os.getenv("FOLDER_ID")

credenciales_dict = json.loads(os.getenv("GOOGLE_CREDENTIALS_JSON"))

credentials = service_account.Credentials.from_service_account_info(
    credenciales_dict, scopes=SCOPES
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
            "INSERT INTO documentos_firmados (cedula, nombres, ruta_pdf, fecha_registro) VALUES (%s, %s, %s, CURRENT_TIMESTAMP)",
            (cedula, nombres, url_drive)
        )
        conn.commit()

        return {"mensaje": "Documento subido y guardado exitosamente", "url": url_drive}

    except Exception as e:
        conn.rollback()
        print(f"⚠️ Error detallado: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/documentos")
async def listar_documentos():
    try:
        cursor.execute("SELECT id, cedula, nombres, ruta_pdf, fecha_registro FROM documentos_firmados ORDER BY id DESC")
        filas = cursor.fetchall()

        documentos = []
        for fila in filas:
            documentos.append({
                "id": fila[0],
                "cedula": fila[1],
                "nombres": fila[2],
                "ruta_pdf": fila[3],
                "fecha_registro": str(fila[4])
            })

        return documentos

    except Exception as e:
        print(f"⚠️ Error detallado: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)
