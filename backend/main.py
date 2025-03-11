from fastapi import FastAPI, Depends, HTTPException, Request, Header
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.orm import Session
import requests
import os
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Dict

# Cargar variables de entorno
load_dotenv()

app = FastAPI()

class Evento(BaseModel):
    summary: str
    description: str
    start: dict
    end: dict
    time_zone: str  # Asegúrate de que este campo está definido
    
# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  ## Puedes restringirlo a ["http://localhost:8100"] si prefieres
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos los métodos (GET, POST, etc.)
    allow_headers=["*"],  # Permite todos los headers
)

# Credenciales de Google
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = "https://19e2-2803-c600-102-864c-9c2a-90c1-aa92-f5e3.ngrok-free.app/auth/callback"

# URLS de Google OAuth
AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Base de datos en memoria (simulación)
usuarios_tokens = {}

@app.get("/auth/google")
def auth_google():
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/calendar.events",
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{AUTH_URL}?{'&'.join([f'{key}={value}' for key, value in params.items()])}"
    return RedirectResponse(auth_url)

# 1️⃣ Endpoint para redirigir al usuario a la autorización de Google
@app.get("/auth/callback")
def auth_callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Código de autorización no encontrado")

    data = {
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    response = requests.post(TOKEN_URL, data=data)
    token_data = response.json()

    if "access_token" not in token_data:
        raise HTTPException(status_code=400, detail="Error al obtener access token")

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")

    # Simulación de base de datos
    user_id = "usuario_demo"  # Aquí deberías obtener el ID real del usuario autenticado
    if user_id not in usuarios_tokens:
        usuarios_tokens[user_id] = {}

    usuarios_tokens[user_id]["access_token"] = access_token
    if refresh_token:
        usuarios_tokens[user_id]["refresh_token"] = refresh_token

    frontend_url = f"http://localhost:8100/home?access_token={access_token}"
    return RedirectResponse(frontend_url)

def refresh_access_token(user_id):
    if user_id not in usuarios_tokens or "refresh_token" not in usuarios_tokens[user_id]:
        raise HTTPException(status_code=400, detail="No se encontró refresh token")

    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": usuarios_tokens[user_id]["refresh_token"],
        "grant_type": "refresh_token",
    }

    response = requests.post(TOKEN_URL, data=data)
    new_token_data = response.json()

    if "access_token" not in new_token_data:
        raise HTTPException(status_code=400, detail="Error al refrescar access token")

    # Guardamos el nuevo access token
    usuarios_tokens[user_id]["access_token"] = new_token_data["access_token"]
    return new_token_data["access_token"]

@app.post("/crear-evento")
def crear_evento_google_calendar(evento: Evento, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=400, detail="Access Token requerido")

    access_token = authorization.split("Bearer ")[1]
    user_id = "usuario_demo"  # Deberías obtenerlo desde el JWT del usuario en un caso real

    try:
        creds = Credentials(token=access_token)
        service = build("calendar", "v3", credentials=creds)
    except Exception:
        # Si el token ha expirado, intentamos refrescarlo
        access_token = refresh_access_token(user_id)
        creds = Credentials(token=access_token)
        service = build("calendar", "v3", credentials=creds)

    evento_data = {
        "summary": evento.summary,
        "description": evento.description,
        "start": {
            "dateTime": evento.start['dateTime'],
            "timeZone": evento.start.get("timeZone", "America/Santiago")
        },
        "end": {
            "dateTime": evento.end['dateTime'],
            "timeZone": evento.end.get("timeZone", "America/Santiago")
        }
    }

    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=evento_data, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        raise HTTPException(status_code=response.status_code, detail=response.json())
      
@app.get("/eventos")
def get_google_calendar_events(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=400, detail="Access Token requerido")

    access_token = authorization.split("Bearer ")[1]
    user_id = "usuario_demo"

    try:
        creds = Credentials(token=access_token)
        service = build("calendar", "v3", credentials=creds)
    except Exception:
        access_token = refresh_access_token(user_id)
        creds = Credentials(token=access_token)
        service = build("calendar", "v3", credentials=creds)

    eventos_result = (
        service.events()
        .list(calendarId="primary", maxResults=10, singleEvents=True, orderBy="startTime")
        .execute()
    )
    eventos = eventos_result.get("items", [])
    return {"eventos": eventos}