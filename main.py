from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os
import psycopg2
import json

app = FastAPI()

# Configura los orígenes permitidos
origins = [
    "http://localhost:5173",  # Para desarrollo local de React
    "https://voltaren-firma.netlify.app",  # Si más adelante lo subes a Netlify o similar
    "https://voltaren-firma-back.onrender.com"  # El propio backend, opcionalmente
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Lista de orígenes permitidos
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos los métodos (GET, POST, etc.)
    allow_headers=["*"],  # Permite todos los headers
)

# Configuración PostgreSQL
conn = psycopg2.connect(
    dbname='postgres',
    user='postgres',
    password='zxYWPzIoxdRrBlNKwrgheRjASewasWjR',  # Reemplaza por variable de entorno en producción
    host='metro.proxy.rlwy.net',
    port='30456'
)
cursor = conn.cursor()

# Google Drive configuración usando variable de entorno
SCOPES = ['https://www.googleapis.com/auth/drive']
FOLDER_ID = '19J-DuhWgbGyM_LpOQIjpOMF39p0umw_0'  # Asegúrate de que esta carpeta exista en tu Drive

# Leer credenciales desde variable de entorno
google_credentials_json = os.environ.get('GOOGLE_CREDENTIALS')

if not google_credentials_json:
    raise Exception("🚨 No se encontró la variable GOOGLE_CREDENTIALS en el entorno")

credentials_dict = json.loads(google_credentials_json)
credentials = service_account.Credentials.from_service_account_info(credentials_dict, scopes=SCOPES)

drive_service = build('drive', 'v3', credentials=credentials)

# Carpeta temporal local
os.makedirs("documentos", exist_ok=True)

@app.post("/subir-pdf")
async def subir_pdf(
    cedula: str = Form(...),
    nombres: str = Form(...),
    contacto: str = Form(...),
    file: UploadFile = None
):
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
            """
            INSERT INTO documentos_firmados (cedula, nombres, ruta_pdf, fecha_registro, contacto)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s)
            """,
            (cedula, nombres, url_drive, contacto)
        )
        conn.commit()

        # Eliminar el archivo temporal
        os.remove(ruta_temp)

        return {"mensaje": "Documento subido y guardado exitosamente", "url": url_drive}

    except Exception as e:
        conn.rollback()
        print(f"⚠️ Error detallado: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/documentos")
async def listar_documentos():
    try:
        cursor.execute("""
            SELECT id, cedula, nombres, ruta_pdf, fecha_registro, contacto
            FROM documentos_firmados
            ORDER BY id DESC
        """)
        filas = cursor.fetchall()

        documentos = []
        for fila in filas:
            documentos.append({
                "id": fila[0],
                "cedula": fila[1],
                "nombres": fila[2],
                "ruta_pdf": fila[3],
                "fecha_registro": str(fila[4]),
                "contacto": fila[5]
            })

        return documentos

    except Exception as e:
        print(f"⚠️ Error detallado: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)
