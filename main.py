
from fastapi import FastAPI, Form, Request, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import sqlite3
from datetime import datetime
from pathlib import Path
import shutil
import uuid
import html
import pandas as pd
import json
import asyncio
from typing import Dict, List, Optional, Set


DB = "supervisores.db"
UPLOAD_DIR = Path("evidencias_supervisores")
EXPORT_DIR = Path("exports_supervisores")
UPLOAD_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)

LOGO_URL = "/static/img/logo.png"

SUCURSALES = [
    "LARREA","ROSEDAL","CONGRESO","ARGENTINA","AV DE MAYI","BELGRANO","BERNAL",
    "CASEROS","CERCANIAS","LAS FLORES","SOY DEL SOL","SUR SA","DIAMANDY","ALTO",
    "FACTORY S","LA RECOVA","MAGA","MEGASOL","NORTE","N50","N ERA S","VENTURA",
    "Q OESTE","ARTESANAL","ARENALES","CALLAO","FRANCO","LAIGLON","NUEVA NORTE",
    "SOCIAL ONCE","SAINT ETIENNE","SAN NICOLAS","VITAL","ZEUS","OBRAS","SANAR 1",
    "SANAR 10","SANAR 11","SANAR 12","SANAR 2","SANAR 4","SANAR 5","SANAR 52",
    "SANAR 59","SANAR 6","SANAR 7","SANAR 8","SANAR 9","SANAR 3","BERAZATEGUI",
    "SOL WILDE","SOLANO","SOY QUILMES","FAR","LUNA","SOY SALUD","TOFANELLI",
    "VARELA","ZAPIOLA","SANAR 60","SANAR 61","SANAR 62","SANAR 63","SANAR 64",
    "SANAR 65","SANAR 66","SANAR 67","SANAR 68","SANAR 69"
]

CATEGORIAS = [
    "Limpieza",
    "Stock",
    "Atención al cliente",
    "Precios",
    "Sistema",
    "Mantenimiento",
    "Imagen / cartelería",
    "Administración",
    "Personal",
    "Otra"
]

PRIORIDADES = ["Baja", "Media", "Alta", "Crítica"]

USUARIOS = {
    "Usuario1": {"password": "1234", "rol": "supervisor"},
    "Usuario2": {"password": "1234", "rol": "supervisor"},
    "Usuario3": {"password": "1234", "rol": "supervisor"},
    "Usuario4": {"password": "1234", "rol": "supervisor"},
    "Admin1": {"password": "1234", "rol": "gerente"},
    "Admin2": {"password": "1234", "rol": "gerente"},
    "Admin3": {"password": "1234", "rol": "gerente"},
}

sesiones = {}

def esc(valor):
    return html.escape(str(valor or ""))

def crear_tablas():
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS observaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sucursal TEXT NOT NULL,
            supervisor TEXT NOT NULL,
            comentario TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'Pendiente',
            fecha_creacion TEXT NOT NULL,
            fecha_edicion TEXT,
            creado_por TEXT NOT NULL,
            editado_por TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS respuestas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            observacion_id INTEGER NOT NULL,
            usuario TEXT NOT NULL,
            rol TEXT NOT NULL,
            mensaje TEXT NOT NULL,
            fecha TEXT NOT NULL,
            FOREIGN KEY (observacion_id) REFERENCES observaciones(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notificaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_nombre TEXT NOT NULL,
            usuario TEXT NOT NULL,
            rol TEXT NOT NULL,
            estado TEXT NOT NULL,
            sucursal TEXT NOT NULL,
            accion TEXT NOT NULL,
            observacion_id INTEGER,
            fecha TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_mensajes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            remitente TEXT NOT NULL,
            remitente_rol TEXT NOT NULL,
            destinatario TEXT,
            mensaje TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'chat',
            observacion_id INTEGER,
            sucursal TEXT,
            prioridad TEXT,
            fecha TEXT NOT NULL
        )
    """)

    cursor.execute("PRAGMA table_info(observaciones)")
    columnas = [fila[1] for fila in cursor.fetchall()]
    migraciones = {
        "categoria": "ALTER TABLE observaciones ADD COLUMN categoria TEXT NOT NULL DEFAULT 'Otra'",
        "prioridad": "ALTER TABLE observaciones ADD COLUMN prioridad TEXT NOT NULL DEFAULT 'Media'",
        "evidencia_archivo": "ALTER TABLE observaciones ADD COLUMN evidencia_archivo TEXT",
    }

    for columna, sql in migraciones.items():
        if columna not in columnas:
            cursor.execute(sql)

    conn.commit()
    conn.close()

crear_tablas()

app = FastAPI(title="App Supervisores")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/evidencias", StaticFiles(directory=str(UPLOAD_DIR)), name="evidencias")

def parse_fecha(fecha):
    if not fecha:
        return None
    try:
        return datetime.strptime(fecha, "%d/%m/%Y %H:%M:%S")
    except Exception:
        return None

def guardar_evidencia(evidencia: UploadFile | None):
    if not evidencia or not evidencia.filename:
        return None

    nombre_original = Path(evidencia.filename).name
    extension = Path(nombre_original).suffix.lower()
    nombre_seguro = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{extension}"
    destino = UPLOAD_DIR / nombre_seguro

    with destino.open("wb") as buffer:
        shutil.copyfileobj(evidencia.file, buffer)

    return nombre_seguro

def html_base(contenido, modo="app", user=None):
    es_login = modo == "login"
    nav = "" if es_login else f"""
    <nav class="navbar navbar-expand-lg fixed-top app-navbar">
        <div class="container-fluid px-3 px-lg-4">
            <a class="navbar-brand d-flex align-items-center gap-2" href="/">
                <img src="{LOGO_URL}" alt="Soy tu farmacia" class="brand-logo">
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#mainNavbar" aria-controls="mainNavbar" aria-expanded="false" aria-label="Abrir navegación">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="mainNavbar">
                <ul class="navbar-nav ms-auto mb-2 mb-lg-0 align-items-lg-center">
                    <li class="nav-item"><a class="nav-link" href="/">Inicio</a></li>
                    <li class="nav-item"><a class="nav-link" href="/dashboard">Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link" href="/nueva">Nueva observación</a></li>
                    <li class="nav-item"><a class="nav-link" href="/observaciones">Observaciones</a></li>
                    <li class="nav-item"><a class="nav-link nav-logout" href="/logout">Salir</a></li>
                </ul>
            </div>
        </div>
    </nav>
    """
    user_payload = user or {}
    users_payload = [{"nombre": nombre, "rol": data["rol"]} for nombre, data in USUARIOS.items()]
    user_json = json.dumps(user_payload, ensure_ascii=False)
    users_json = json.dumps(users_payload, ensure_ascii=False)
    return f"""
    <!doctype html>
    <html lang="es">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>App Supervisores</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="/static/css/styles.css" rel="stylesheet">
    </head>
    <body class="{'login-mode' if es_login else 'app-mode'}">
        {nav}
        <div class="{'login-shell-wrap' if es_login else 'page-wrap'}">
            {contenido}
        </div>

        <div class="modal fade" id="evidenceModal" tabindex="-1" aria-hidden="true">
            <div class="modal-dialog modal-dialog-centered modal-xl">
                <div class="modal-content border-0 rounded-4 overflow-hidden">
                    <div class="modal-header">
                        <h5 class="modal-title">Evidencia</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button>
                    </div>
                    <div class="modal-body text-center bg-light">
                        <img id="evidenceModalImg" class="img-fluid modal-img rounded-3" alt="Evidencia ampliada">
                    </div>
                </div>
            </div>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            window.APP_USER = {user_json};
            window.APP_USERS = {users_json};
        </script>
        <script src="/static/js/app.js"></script>
    </body>
    </html>
    """

def evidencia_preview_html(nombre_archivo, texto="Ver evidencia"):
    if not nombre_archivo:
        return ""
    archivo = esc(nombre_archivo)
    url = f"/evidencias/{archivo}"
    ext = Path(str(nombre_archivo)).suffix.lower()
    if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]:
        return f"""
        <a class="evidence-link" href="{url}" data-evidence-src="{url}" aria-label="Ampliar evidencia">
            <img class="evidence-thumb" src="{url}" alt="Miniatura de evidencia" loading="lazy">
            <span>{esc(texto)}</span>
        </a>
        """
    return f"<a href='{url}' target='_blank'>{esc(texto)}</a>"

def usuario_actual(request: Request):
    sid = request.cookies.get("sid")
    if not sid or sid not in sesiones:
        return None
    return sesiones[sid]

def requiere_login(request: Request):
    return usuario_actual(request)

def opciones_select(lista, actual="", incluir_todas=False):
    html_opciones = "<option value=''>Todas</option>" if incluir_todas else ""
    for item in lista:
        selected = "selected" if item == actual else ""
        html_opciones += f"<option value='{esc(item)}' {selected}>{esc(item)}</option>"
    return html_opciones

APP_NOMBRE = "App Supervisores"

class ConnectionManager:
    """
    Gestiona conexiones WebSocket activas.
    - active_connections: user_id -> lista de sockets abiertos del mismo usuario.
    - Permite enviar mensajes directos, broadcasts y estados online.
    """
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.lock = asyncio.Lock()

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        async with self.lock:
            self.active_connections.setdefault(user_id, []).append(websocket)
        await self.broadcast_online_status()

    async def disconnect(self, user_id: str, websocket: WebSocket):
        async with self.lock:
            conexiones = self.active_connections.get(user_id, [])
            if websocket in conexiones:
                conexiones.remove(websocket)
            if not conexiones and user_id in self.active_connections:
                del self.active_connections[user_id]
        await self.broadcast_online_status()

    async def send_to_user(self, user_id: str, payload: dict):
        """Envía un mensaje a todas las pestañas/dispositivos conectados de un usuario."""
        async with self.lock:
            conexiones = list(self.active_connections.get(user_id, []))

        conexiones_rotas = []
        for websocket in conexiones:
            try:
                await websocket.send_json(payload)
            except Exception:
                conexiones_rotas.append(websocket)

        if conexiones_rotas:
            async with self.lock:
                actuales = self.active_connections.get(user_id, [])
                for ws in conexiones_rotas:
                    if ws in actuales:
                        actuales.remove(ws)
                if not actuales and user_id in self.active_connections:
                    del self.active_connections[user_id]

    async def broadcast(self, payload: dict):
        """Envía un mensaje a todos los usuarios conectados."""
        async with self.lock:
            usuarios = list(self.active_connections.keys())

        for user_id in usuarios:
            await self.send_to_user(user_id, payload)

    async def broadcast_except(self, payload: dict, exclude_user: str):
        """Envía un mensaje a todos los usuarios conectados excepto al emisor."""
        async with self.lock:
            usuarios = [u for u in self.active_connections.keys() if u != exclude_user]

        for user_id in usuarios:
            await self.send_to_user(user_id, payload)

    async def broadcast_online_status(self):
        async with self.lock:
            usuarios_online = sorted(self.active_connections.keys())

        await self.broadcast({
            "type": "online_status",
            "online": usuarios_online
        })

    def is_online(self, user_id: str) -> bool:
        return user_id in self.active_connections


manager = ConnectionManager()


def guardar_chat_mensaje(remitente, remitente_rol, mensaje, destinatario=None, tipo="chat", observacion_id=None, sucursal=None, prioridad=None):
    """Guarda mensajes realtime en SQLite para que no se pierdan al cerrar sesión."""
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO chat_mensajes
        (remitente, remitente_rol, destinatario, mensaje, tipo, observacion_id, sucursal, prioridad, fecha)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (remitente, remitente_rol, destinatario, mensaje, tipo, observacion_id, sucursal, prioridad, fecha))
    msg_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {
        "id": msg_id,
        "remitente": remitente,
        "remitente_rol": remitente_rol,
        "destinatario": destinatario,
        "mensaje": mensaje,
        "tipo": tipo,
        "observacion_id": observacion_id,
        "sucursal": sucursal,
        "prioridad": prioridad,
        "fecha": fecha,
    }


def obtener_chat_mensajes(usuario, limite=60):
    """Trae mensajes generales, enviados al usuario o enviados por el usuario."""
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, remitente, remitente_rol, destinatario, mensaje, tipo, observacion_id, sucursal, prioridad, fecha
        FROM chat_mensajes
        WHERE destinatario IS NULL OR destinatario = ? OR remitente = ?
        ORDER BY id DESC
        LIMIT ?
    """, (usuario, usuario, limite))
    rows = cursor.fetchall()
    conn.close()

    mensajes = []
    for r in reversed(rows):
        mensajes.append({
            "id": r[0],
            "remitente": r[1],
            "remitente_rol": r[2],
            "destinatario": r[3],
            "mensaje": r[4],
            "tipo": r[5],
            "observacion_id": r[6],
            "sucursal": r[7],
            "prioridad": r[8],
            "fecha": r[9],
        })
    return mensajes


def registrar_notificacion(usuario, rol, estado, sucursal, accion, observacion_id=None):
    """Registra eventos para las notificaciones del navegador y devuelve el ID creado."""
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notificaciones
        (app_nombre, usuario, rol, estado, sucursal, accion, observacion_id, fecha)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (APP_NOMBRE, usuario, rol, estado, sucursal, accion, observacion_id, fecha))
    notif_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return notif_id

@app.get("/api/notificaciones")
def api_notificaciones(request: Request, after: int = 0):
    user = requiere_login(request)
    if not user:
        return JSONResponse({"ok": False, "notificaciones": []}, status_code=401)

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, app_nombre, usuario, rol, estado, sucursal, accion, observacion_id, fecha
        FROM notificaciones
        WHERE id > ? AND usuario != ?
        ORDER BY id ASC
        LIMIT 20
    """, (after, user["nombre"]))
    rows = cursor.fetchall()
    conn.close()

    notificaciones = []
    for r in rows:
        cuerpo = f"{r[6]} · {r[2]} ({r[3]}) · Estado: {r[4]} · Sucursal: {r[5]}"
        notificaciones.append({
            "id": r[0],
            "app_nombre": r[1],
            "usuario": r[2],
            "rol": r[3],
            "estado": r[4],
            "sucursal": r[5],
            "accion": r[6],
            "observacion_id": r[7],
            "fecha": r[8],
            "titulo": r[1],
            "cuerpo": cuerpo,
        })
    return {"ok": True, "notificaciones": notificaciones}

@app.get("/api/notificaciones/ultimo")
def api_notificaciones_ultimo(request: Request):
    user = requiere_login(request)
    if not user:
        return JSONResponse({"ok": False, "ultimo_id": 0}, status_code=401)

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(MAX(id), 0) FROM notificaciones")
    ultimo_id = cursor.fetchone()[0]
    conn.close()
    return {"ok": True, "ultimo_id": ultimo_id}


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """
    Canal realtime del usuario.
    Mensajes esperados:
    {
      "type": "chat_message",
      "to": "Usuario1" | null,
      "message": "texto"
    }
    """
    if user_id not in USUARIOS:
        await websocket.close(code=1008)
        return

    await manager.connect(user_id, websocket)

    try:
        # Enviar historial inicial al conectarse.
        user_info = USUARIOS.get(user_id, {})
        await websocket.send_json({
            "type": "chat_history",
            "messages": obtener_chat_mensajes(user_id)
        })

        while True:
            raw_data = await websocket.receive_text()

            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Formato inválido."
                })
                continue

            event_type = data.get("type")

            if event_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if event_type == "chat_message":
                mensaje = str(data.get("message", "")).strip()
                destinatario = data.get("to") or None

                if not mensaje:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No se puede enviar un mensaje vacío."
                    })
                    continue

                if destinatario and destinatario not in USUARIOS:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Destinatario inexistente."
                    })
                    continue

                payload_msg = guardar_chat_mensaje(
                    remitente=user_id,
                    remitente_rol=user_info.get("rol", ""),
                    destinatario=destinatario,
                    mensaje=mensaje,
                    tipo="chat"
                )

                payload = {
                    "type": "chat_message",
                    "message": payload_msg
                }

                # Mensaje directo: va al destinatario y queda reflejado en el remitente.
                if destinatario:
                    await manager.send_to_user(destinatario, payload)
                    await manager.send_to_user(user_id, payload)
                else:
                    # Sin destinatario: broadcast general.
                    await manager.broadcast(payload)

            else:
                await websocket.send_json({
                    "type": "error",
                    "message": "Tipo de evento no soportado."
                })

    except WebSocketDisconnect:
        await manager.disconnect(user_id, websocket)
    except Exception:
        # Desconexión robusta ante errores de red o cierres abruptos.
        await manager.disconnect(user_id, websocket)


@app.get("/api/chat/mensajes")
def api_chat_mensajes(request: Request):
    user = requiere_login(request)
    if not user:
        return JSONResponse({"ok": False, "messages": []}, status_code=401)
    return {"ok": True, "messages": obtener_chat_mensajes(user["nombre"])}


@app.get("/api/usuarios")
def api_usuarios(request: Request):
    user = requiere_login(request)
    if not user:
        return JSONResponse({"ok": False, "usuarios": []}, status_code=401)

    usuarios = []
    for nombre, info in USUARIOS.items():
        usuarios.append({
            "nombre": nombre,
            "rol": info["rol"],
            "online": manager.is_online(nombre),
        })
    return {"ok": True, "usuarios": usuarios}

@app.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    user = usuario_actual(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    contenido = f"""
    <main class="app-home">
        <div class="card hero-card">
            <h1>App Supervisores</h1>
            <div class="user-pill">
                <span>Usuario: <b>{esc(user['nombre'])}</b></span>
                <span>|</span>
                <span>Rol: <b>{esc(user['rol'])}</b></span>
            </div>

            <div class="menu-grid">
                <a class="menu-card" href="/dashboard"><b>Dashboard de gestión</b><span>Indicadores, rankings, categorías, prioridades y evolución.</span></a>
                <a class="menu-card" href="/nueva"><b>Cargar nueva observación</b><span>Registrar novedades con prioridad, categoría y evidencia.</span></a>
                <a class="menu-card" href="/observaciones"><b>Ver observaciones</b><span>Consultar, filtrar, exportar y responder seguimientos.</span></a>
                <a class="menu-card logout" href="/logout"><b>Cerrar sesión</b><span>Salir del sistema de forma segura.</span></a>
            </div>
        </div>
    </main>
    """
    return html_base(contenido, user=user)

@app.get("/login", response_class=HTMLResponse)
def login_form():
    opciones = "".join([f"<option value='{esc(u)}'>{esc(u)}</option>" for u in USUARIOS.keys()])
    contenido = f"""
    <div class="login-shell">
        <section class="login-brand">
            <div class="login-logo-card">
                <img src="{LOGO_URL}" alt="Soy tu farmacia">
            </div>
            <h1>Gestión de sucursales</h1>
            <p>Módulo de Auditoría.</p>
        </section>

        <section class="card login-card">
            <h2>Ingreso al sistema</h2>
            <p class="small-muted">Seleccioná tu usuario e ingresá la contraseña para continuar.</p>
            <form action="/login" method="post">
                <label>Usuario</label>
                <select name="usuario">{opciones}</select>
                <label>Contraseña</label>
                <input type="password" name="password" required>
                <button type="submit">Ingresar</button>
            </form>
            <p class="small-muted">Contraseña inicial: <b>1234</b></p>
        </section>
    </div>
    """
    return html_base(contenido, modo="login")

@app.post("/login")
def login(usuario: str = Form(...), password: str = Form(...)):
    if usuario not in USUARIOS or USUARIOS[usuario]["password"] != password:
        return HTMLResponse(html_base("<div class='card'><h3>Usuario o contraseña incorrectos</h3><a href='/login'>Volver</a></div>"))

    sid = f"{usuario}_{datetime.now().timestamp()}"
    sesiones[sid] = {"nombre": usuario, "rol": USUARIOS[usuario]["rol"]}
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="sid", value=sid)
    return response

@app.get("/logout")
def logout(request: Request):
    sid = request.cookies.get("sid")
    if sid in sesiones:
        del sesiones[sid]
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("sid")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = requiere_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM observaciones")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM observaciones WHERE estado = 'Pendiente'")
    pendientes = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM observaciones WHERE estado = 'Resuelto'")
    resueltas = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM observaciones WHERE estado = 'Pendiente' AND prioridad IN ('Alta','Crítica')")
    pendientes_criticas = cursor.fetchone()[0]

    porcentaje_resuelto = round((resueltas / total) * 100, 1) if total else 0

    cursor.execute("""
        SELECT sucursal, COUNT(*) as cantidad
        FROM observaciones
        GROUP BY sucursal
        ORDER BY cantidad DESC
        LIMIT 10
    """)
    ranking_sucursales = cursor.fetchall()

    cursor.execute("""
        SELECT supervisor, COUNT(*) as cantidad
        FROM observaciones
        GROUP BY supervisor
        ORDER BY cantidad DESC
    """)
    ranking_supervisores = cursor.fetchall()

    cursor.execute("""
        SELECT categoria, COUNT(*) as cantidad
        FROM observaciones
        GROUP BY categoria
        ORDER BY cantidad DESC
    """)
    ranking_categorias = cursor.fetchall()

    cursor.execute("""
        SELECT prioridad, COUNT(*) as cantidad
        FROM observaciones
        GROUP BY prioridad
        ORDER BY CASE prioridad WHEN 'Crítica' THEN 1 WHEN 'Alta' THEN 2 WHEN 'Media' THEN 3 ELSE 4 END
    """)
    ranking_prioridades = cursor.fetchall()

    cursor.execute("""
        SELECT strftime('%Y-%m', substr(fecha_creacion,7,4) || '-' || substr(fecha_creacion,4,2) || '-' || substr(fecha_creacion,1,2)) as mes,
               COUNT(*) as cantidad
        FROM observaciones
        GROUP BY mes
        ORDER BY mes DESC
        LIMIT 12
    """)
    evolucion_mensual = cursor.fetchall()

    cursor.execute("""
        SELECT id, sucursal, supervisor, categoria, prioridad, comentario, fecha_creacion
        FROM observaciones
        WHERE estado = 'Pendiente'
        ORDER BY id ASC
    """)
    pendientes_raw = cursor.fetchall()

    cursor.execute("""
        SELECT fecha_creacion, fecha_edicion
        FROM observaciones
        WHERE estado = 'Resuelto'
          AND fecha_creacion IS NOT NULL
          AND fecha_edicion IS NOT NULL
    """)
    resueltas_raw = cursor.fetchall()

    cursor.execute("""
        SELECT sucursal, categoria, COUNT(*) as cantidad
        FROM observaciones
        GROUP BY sucursal, categoria
        HAVING COUNT(*) >= 2
        ORDER BY cantidad DESC
        LIMIT 15
    """)
    reincidencias = cursor.fetchall()

    conn.close()

    ahora = datetime.now()
    pendientes_antiguas = []
    for id_, sucursal, supervisor, categoria, prioridad, comentario, fecha_creacion in pendientes_raw:
        fecha_dt = parse_fecha(fecha_creacion)
        if fecha_dt:
            dias = (ahora - fecha_dt).days
            if dias >= 7:
                comentario_corto = comentario[:100] + "..." if len(comentario) > 100 else comentario
                pendientes_antiguas.append((id_, sucursal, supervisor, categoria, prioridad, comentario_corto, fecha_creacion, dias))

    tiempos = []
    for fecha_creacion, fecha_edicion in resueltas_raw:
        fc = parse_fecha(fecha_creacion)
        fe = parse_fecha(fecha_edicion)
        if fc and fe and fe >= fc:
            tiempos.append((fe - fc).total_seconds() / 3600)

    if tiempos:
        promedio_horas = sum(tiempos) / len(tiempos)
        tiempo_promedio = f"{round(promedio_horas, 1)} hs" if promedio_horas < 24 else f"{round(promedio_horas / 24, 1)} días"
    else:
        tiempo_promedio = "Sin datos"

    def filas_dos_columnas(datos, url_base, nombre_col):
        filas = ""
        for nombre, cantidad in datos:
            filas += f"<tr><td><a href='{url_base}{esc(nombre)}'>{esc(nombre)}</a></td><td>{cantidad}</td></tr>"
        return filas or f"<tr><td colspan='2'>Sin datos</td></tr>"

    filas_sucursales = filas_dos_columnas(ranking_sucursales, "/observaciones?sucursal_filtro=", "Sucursal")
    filas_supervisores = filas_dos_columnas(ranking_supervisores, "/observaciones?supervisor_filtro=", "Supervisor")
    filas_categorias = filas_dos_columnas(ranking_categorias, "/observaciones?categoria_filtro=", "Categoría")
    filas_prioridades = filas_dos_columnas(ranking_prioridades, "/observaciones?prioridad_filtro=", "Prioridad")

    filas_evolucion = ""
    for mes, cantidad in reversed(evolucion_mensual):
        filas_evolucion += f"<tr><td>{esc(mes or 'Sin fecha')}</td><td>{cantidad}</td></tr>"
    if not filas_evolucion:
        filas_evolucion = "<tr><td colspan='2'>Sin datos</td></tr>"

    filas_reincidencias = ""
    for sucursal, categoria, cantidad in reincidencias:
        filas_reincidencias += f"""
        <tr>
            <td><a href="/observaciones?sucursal_filtro={esc(sucursal)}&categoria_filtro={esc(categoria)}">{esc(sucursal)}</a></td>
            <td>{esc(categoria)}</td>
            <td>{cantidad}</td>
        </tr>
        """
    if not filas_reincidencias:
        filas_reincidencias = "<tr><td colspan='3'>Sin reincidencias detectadas.</td></tr>"

    filas_pendientes_antiguas = ""
    for id_, sucursal, supervisor, categoria, prioridad, comentario, fecha_creacion, dias in pendientes_antiguas:
        prioridad_clase = prioridad.lower().replace("í", "i")
        filas_pendientes_antiguas += f"""
        <tr>
            <td>{id_}</td>
            <td>{esc(sucursal)}</td>
            <td>{esc(supervisor)}</td>
            <td>{esc(categoria)}</td>
            <td><span class="prioridad-{prioridad_clase}">{esc(prioridad)}</span></td>
            <td>{esc(fecha_creacion)}</td>
            <td>{dias} días</td>
            <td>{esc(comentario)}</td>
            <td><a href="/chat/{id_}">Ver conversación</a></td>
        </tr>
        """
    if not filas_pendientes_antiguas:
        filas_pendientes_antiguas = "<tr><td colspan='9'>No hay pendientes con más de 7 días.</td></tr>"

    contenido = f"""
    <div class="card">
        <h2 class="section-title">Dashboard de gestión</h2>
        <p>Usuario: <b>{esc(user['nombre'])}</b> | Rol: <b>{esc(user['rol'])}</b></p>
        <p>
            <a href="/">Inicio</a> |
            <a href="/observaciones">Ver observaciones</a> |
            <a href="/nueva">Nueva observación</a>
        </p>
    </div>

    <div class="dashboard-grid">
        <div class="metric-card neutral" data-metric="total"><h3>Total observaciones</h3><p>{total}</p></div>
        <div class="metric-card warning" data-metric="pendientes"><h3>Pendientes</h3><p>{pendientes}</p></div>
        <div class="metric-card success" data-metric="resueltas"><h3>Resueltas</h3><p>{resueltas}</p></div>
        <div class="metric-card" data-metric="porcentaje"><h3>% resolución</h3><p>{porcentaje_resuelto}%</p></div>
        <div class="metric-card"><h3>Tiempo promedio solución</h3><p>{tiempo_promedio}</p></div>
        <div class="metric-card warning"><h3>Pendientes +7 días</h3><p>{len(pendientes_antiguas)}</p></div>
        <div class="metric-card danger" data-metric="criticas"><h3>Pendientes alta/crítica</h3><p>{pendientes_criticas}</p></div>
        <div class="metric-card"><h3>Reincidencias</h3><p>{len(reincidencias)}</p></div>
    </div>

    <div class="two-col">
        <div class="card">
            <h3>Ranking de sucursales</h3>
            <table><tr><th>Sucursal</th><th>Cantidad</th></tr>{filas_sucursales}</table>
        </div>
        <div class="card">
            <h3>Ranking por supervisor</h3>
            <table><tr><th>Supervisor</th><th>Cantidad</th></tr>{filas_supervisores}</table>
        </div>
    </div>

    <div class="two-col">
        <div class="card">
            <h3>Categorías de observación</h3>
            <table><tr><th>Categoría</th><th>Cantidad</th></tr>{filas_categorias}</table>
        </div>
        <div class="card">
            <h3>Prioridades</h3>
            <table><tr><th>Prioridad</th><th>Cantidad</th></tr>{filas_prioridades}</table>
        </div>
    </div>

    <div class="two-col">
        <div class="card">
            <h3>Evolución mensual</h3>
            <p class="small-muted">Permite ver si las observaciones suben o bajan con el tiempo.</p>
            <table><tr><th>Mes</th><th>Cantidad</th></tr>{filas_evolucion}</table>
        </div>
        <div class="card">
            <h3>Reincidencias por sucursal y categoría</h3>
            <p class="small-muted">Se marca cuando una sucursal acumula 2 o más observaciones de la misma categoría.</p>
            <table><tr><th>Sucursal</th><th>Categoría</th><th>Cantidad</th></tr>{filas_reincidencias}</table>
        </div>
    </div>

    <div class="card">
        <h3>Pendientes antiguas</h3>
        <p class="small-muted">Se consideran antiguas las observaciones pendientes con 7 días o más.</p>
        <table>
            <tr>
                <th>ID</th><th>Sucursal</th><th>Supervisor</th><th>Categoría</th><th>Prioridad</th>
                <th>Fecha creación</th><th>Antigüedad</th><th>Comentario</th><th>Acción</th>
            </tr>
            {filas_pendientes_antiguas}
        </table>
    </div>
    """
    return html_base(contenido, user=user)

@app.get("/nueva", response_class=HTMLResponse)
def nueva(request: Request):
    user = requiere_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    contenido = f"""
    <div class="card">
        <h2>Nueva observación</h2>
        <p>Cargando como: <b>{esc(user['nombre'])}</b></p>

        <form action="/guardar" method="post" enctype="multipart/form-data">
            <label>Sucursal</label>
            <select name="sucursal" required>{opciones_select(SUCURSALES)}</select>

            <label>Categoría</label>
            <select name="categoria" required>{opciones_select(CATEGORIAS, "Otra")}</select>

            <label>Prioridad</label>
            <select name="prioridad" required>{opciones_select(PRIORIDADES, "Media")}</select>

            <label>Comentario</label>
            <textarea name="comentario" rows="5" required></textarea>

            <label>Evidencia / imagen adjunta (opcional)</label>
            <input type="file" name="evidencia">

            <button type="submit">Guardar</button>
        </form>

        <br>
        <a href="/">Volver</a>
    </div>
    """
    return html_base(contenido, user=user)

@app.post("/guardar")
async def guardar(
    request: Request,
    sucursal: str = Form(...),
    categoria: str = Form(...),
    prioridad: str = Form(...),
    comentario: str = Form(...),
    evidencia: UploadFile = File(None)
):
    user = requiere_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if categoria not in CATEGORIAS:
        categoria = "Otra"
    if prioridad not in PRIORIDADES:
        prioridad = "Media"

    fecha = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    evidencia_archivo = guardar_evidencia(evidencia)

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO observaciones 
        (sucursal, supervisor, categoria, prioridad, comentario, estado, fecha_creacion, fecha_edicion, creado_por, editado_por, evidencia_archivo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (sucursal, user["nombre"], categoria, prioridad, comentario, "Pendiente", fecha, None, user["nombre"], None, evidencia_archivo))
    observacion_id = cursor.lastrowid
    conn.commit()
    conn.close()

    notif_id = registrar_notificacion(
        usuario=user["nombre"],
        rol=user["rol"],
        estado="Pendiente",
        sucursal=sucursal,
        accion="Nueva observación",
        observacion_id=observacion_id,
    )

    # Evento realtime para Dashboard, Observaciones y Toasts.
    observacion_evento = {
        "id": observacion_id,
        "fecha_creacion": fecha,
        "sucursal": sucursal,
        "supervisor": user["nombre"],
        "categoria": categoria,
        "prioridad": prioridad,
        "comentario": comentario,
        "estado": "Pendiente",
        "fecha_edicion": None,
        "editado_por": None,
        "creado_por": user["nombre"],
        "evidencia_archivo": evidencia_archivo,
    }

    await manager.broadcast_except({
        "type": "nueva_observacion",
        "from": user["nombre"],
        "notification_id": notif_id,
        "title": APP_NOMBRE,
        "message": f"Nueva observación detectada en la sucursal {sucursal}",
        "estado": "Pendiente",
        "sucursal": sucursal,
        "prioridad": prioridad,
        "observacion_id": observacion_id,
        "critical": prioridad == "Crítica",
        "observacion": observacion_evento,
    }, exclude_user=user["nombre"])

    return RedirectResponse(url="/observaciones", status_code=303)

@app.get("/observaciones", response_class=HTMLResponse)
def observaciones(
    request: Request,
    sucursal_filtro: str = "",
    estado_filtro: str = "",
    supervisor_filtro: str = "",
    categoria_filtro: str = "",
    prioridad_filtro: str = ""
):
    user = requiere_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    query = """
        SELECT id, sucursal, supervisor, categoria, prioridad, comentario, estado, fecha_creacion, fecha_edicion, creado_por, editado_por, evidencia_archivo
        FROM observaciones
        WHERE 1=1
    """
    params = []

    if sucursal_filtro:
        query += " AND sucursal LIKE ?"
        params.append(f"%{sucursal_filtro}%")
    if estado_filtro:
        query += " AND estado = ?"
        params.append(estado_filtro)
    if supervisor_filtro:
        query += " AND supervisor = ?"
        params.append(supervisor_filtro)
    if categoria_filtro:
        query += " AND categoria = ?"
        params.append(categoria_filtro)
    if prioridad_filtro:
        query += " AND prioridad = ?"
        params.append(prioridad_filtro)

    query += " ORDER BY id DESC"
    cursor.execute(query, params)
    datos = cursor.fetchall()
    conn.close()

    supervisores = ["Usuario1", "Usuario2", "Usuario3", "Usuario4"]
    opciones_estado = "".join([f"<option value='{esc(e)}' {'selected' if e == estado_filtro else ''}>{'Todos' if e == '' else esc(e)}</option>" for e in ["", "Pendiente", "Resuelto"]])

    filas = ""
    for id_, sucursal, supervisor, categoria, prioridad, comentario, estado, fecha_creacion, fecha_edicion, creado_por, editado_por, evidencia_archivo in datos:
        puede_editar = user["rol"] in ["gerente"] or creado_por == user["nombre"]
        puede_resolver = user["rol"] in ["gerente"]
        acciones = f"<a href='/chat/{id_}'>Ver conversación / Responder</a><br>"
        if evidencia_archivo:
            acciones += evidencia_preview_html(evidencia_archivo) + "<br>"
        if puede_editar:
            acciones += f"<a href='/editar/{id_}'>Editar observación</a><br>"
        if puede_resolver and estado != "Resuelto":
            acciones += f"""
            <form action="/resolver/{id_}" method="post" style="margin-top:6px;">
                <button type="submit">Marcar resuelto</button>
            </form>
            """

        clase_estado = "resuelto" if estado == "Resuelto" else "pendiente"
        prioridad_clase = prioridad.lower().replace("í", "i")
        comentario_corto = comentario[:120] + "..." if len(comentario) > 120 else comentario

        filas += f"""
        <tr>
            <td>{id_}</td>
            <td>{esc(fecha_creacion)}</td>
            <td>{esc(sucursal)}</td>
            <td>{esc(supervisor)}</td>
            <td><span class="tag">{esc(categoria)}</span></td>
            <td><span class="prioridad-{prioridad_clase}">{esc(prioridad)}</span></td>
            <td>{esc(comentario_corto)}</td>
            <td class="{clase_estado}">{esc(estado)}</td>
            <td>{esc(fecha_edicion)}</td>
            <td>{esc(editado_por)}</td>
            <td>{acciones}</td>
        </tr>
        """

    filtros_avanzados_activos = any([estado_filtro, supervisor_filtro, categoria_filtro, prioridad_filtro])
    texto_filtros = "Filtros avanzados activos" if filtros_avanzados_activos else "Mostrar filtros avanzados"
    export_url = f"/exportar?sucursal_filtro={esc(sucursal_filtro)}&estado_filtro={esc(estado_filtro)}&supervisor_filtro={esc(supervisor_filtro)}&categoria_filtro={esc(categoria_filtro)}&prioridad_filtro={esc(prioridad_filtro)}"

    contenido = f"""
    <div class="card-2">
        <h2>Observaciones</h2>
        <p>Usuario: <b>{esc(user['nombre'])}</b> | Rol: <b>{esc(user['rol'])}</b></p>
    </div>

    <div class="card filtros-card">
        <div class="barra-filtros">
            <button type="button" onclick="toggleFiltros()">{texto_filtros}</button>
            <div class="total-filter"><b>Total:</b> {len(datos)}</div>

            <form action="/observaciones" method="get" class="busqueda-rapida">
                <input type="text" name="sucursal_filtro" placeholder="Buscar sucursal..." value="{esc(sucursal_filtro)}" autocomplete="off">
                <input type="hidden" name="estado_filtro" value="{esc(estado_filtro)}">
                <input type="hidden" name="supervisor_filtro" value="{esc(supervisor_filtro)}">
                <input type="hidden" name="categoria_filtro" value="{esc(categoria_filtro)}">
                <input type="hidden" name="prioridad_filtro" value="{esc(prioridad_filtro)}">
                <button type="submit">Buscar</button>
            </form>

            <a class="limpiar-link" href="/observaciones">Limpiar</a>
        </div>

        <div id="panelFiltros" style="display:{'block' if filtros_avanzados_activos else 'none'}; margin-top:15px;">
            <form action="/observaciones" method="get">
                <label>Filtrar por sucursal</label>
                <select name="sucursal_filtro">{opciones_select(SUCURSALES, sucursal_filtro, True)}</select>

                <label>Filtrar por estado</label>
                <select name="estado_filtro">{opciones_estado}</select>

                <label>Filtrar por supervisor</label>
                <select name="supervisor_filtro">{opciones_select(supervisores, supervisor_filtro, True)}</select>

                <label>Filtrar por categoría</label>
                <select name="categoria_filtro">{opciones_select(CATEGORIAS, categoria_filtro, True)}</select>

                <label>Filtrar por prioridad</label>
                <select name="prioridad_filtro">{opciones_select(PRIORIDADES, prioridad_filtro, True)}</select>

                <button type="submit">Aplicar filtros avanzados</button>
                <a href="/observaciones" style="margin-left:10px;">Limpiar filtros</a>
            </form>
        </div>
    </div>

    <table id="observacionesTable" data-live-observaciones="1">
        <thead>
        <tr>
            <th>ID</th><th>Fecha creación</th><th>Sucursal</th><th>Supervisor</th><th>Categoría</th><th>Prioridad</th>
            <th>Comentario</th><th>Estado</th><th>Fecha edición</th><th>Editado por</th><th>Acciones</th>
        </tr>
        </thead>
        <tbody id="observacionesTableBody">
        {filas or "<tr data-empty-row='1'><td colspan='11'>No hay observaciones para los filtros seleccionados.</td></tr>"}
        </tbody>
    </table>

    <script>
        function toggleFiltros() {{
            const panel = document.getElementById("panelFiltros");
            panel.style.display = panel.style.display === "none" ? "block" : "none";
        }}
    </script>
    """
    return html_base(contenido, user=user)

@app.get("/exportar")
def exportar(
    request: Request,
    sucursal_filtro: str = "",
    estado_filtro: str = "",
    supervisor_filtro: str = "",
    categoria_filtro: str = "",
    prioridad_filtro: str = ""
):
    user = requiere_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    conn = sqlite3.connect(DB)

    query = """
        SELECT id, fecha_creacion, sucursal, supervisor, categoria, prioridad, comentario, estado, fecha_edicion, creado_por, editado_por, evidencia_archivo
        FROM observaciones
        WHERE 1=1
    """
    params = []
    if sucursal_filtro:
        query += " AND sucursal LIKE ?"
        params.append(f"%{sucursal_filtro}%")
    if estado_filtro:
        query += " AND estado = ?"
        params.append(estado_filtro)
    if supervisor_filtro:
        query += " AND supervisor = ?"
        params.append(supervisor_filtro)
    if categoria_filtro:
        query += " AND categoria = ?"
        params.append(categoria_filtro)
    if prioridad_filtro:
        query += " AND prioridad = ?"
        params.append(prioridad_filtro)
    query += " ORDER BY id DESC"

    df = pd.read_sql_query(query, conn, params=params)

    resumen_sucursal = pd.read_sql_query("""
        SELECT sucursal, 
               COUNT(*) AS total,
               SUM(CASE WHEN estado='Pendiente' THEN 1 ELSE 0 END) AS pendientes,
               SUM(CASE WHEN estado='Resuelto' THEN 1 ELSE 0 END) AS resueltas
        FROM observaciones
        GROUP BY sucursal
        ORDER BY total DESC
    """, conn)

    resumen_categoria = pd.read_sql_query("""
        SELECT categoria, COUNT(*) AS total
        FROM observaciones
        GROUP BY categoria
        ORDER BY total DESC
    """, conn)

    reincidencias = pd.read_sql_query("""
        SELECT sucursal, categoria, COUNT(*) AS cantidad
        FROM observaciones
        GROUP BY sucursal, categoria
        HAVING COUNT(*) >= 2
        ORDER BY cantidad DESC
    """, conn)

    conn.close()

    archivo = EXPORT_DIR / f"observaciones_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    with pd.ExcelWriter(archivo, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Observaciones")
        resumen_sucursal.to_excel(writer, index=False, sheet_name="Resumen sucursal")
        resumen_categoria.to_excel(writer, index=False, sheet_name="Resumen categoria")
        reincidencias.to_excel(writer, index=False, sheet_name="Reincidencias")

    return FileResponse(
        path=str(archivo),
        filename=archivo.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.get("/editar/{id_obs}", response_class=HTMLResponse)
def editar_form(request: Request, id_obs: int):
    user = requiere_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("SELECT id, sucursal, categoria, prioridad, comentario, creado_por, evidencia_archivo FROM observaciones WHERE id = ?", (id_obs,))
    obs = cursor.fetchone()
    conn.close()

    if not obs:
        return HTMLResponse(html_base("<div class='card'><h3>Observación no encontrada</h3><a href='/observaciones'>Volver</a></div>"))

    id_, sucursal_actual, categoria_actual, prioridad_actual, comentario_actual, creado_por, evidencia_archivo = obs
    puede_editar = user["rol"] in ["gerente"] or creado_por == user["nombre"]

    if not puede_editar:
        return HTMLResponse(html_base("<div class='card'><h3>No tenés permiso para editar esta observación</h3><a href='/observaciones'>Volver</a></div>"))

    evidencia_html = ""
    if evidencia_archivo:
        evidencia_html = f"<p><b>Evidencia actual:</b></p>{evidencia_preview_html(evidencia_archivo, 'Ampliar evidencia actual')}"

    contenido = f"""
    <div class="card">
        <h2>Editar observación #{id_}</h2>
        {evidencia_html}
        <form action="/editar/{id_}" method="post" enctype="multipart/form-data">
            <label>Sucursal</label>
            <select name="sucursal" required>{opciones_select(SUCURSALES, sucursal_actual)}</select>

            <label>Categoría</label>
            <select name="categoria" required>{opciones_select(CATEGORIAS, categoria_actual)}</select>

            <label>Prioridad</label>
            <select name="prioridad" required>{opciones_select(PRIORIDADES, prioridad_actual)}</select>

            <label>Comentario</label>
            <textarea name="comentario" rows="5" required>{esc(comentario_actual)}</textarea>

            <label>Reemplazar evidencia / imagen adjunta (opcional)</label>
            <input type="file" name="evidencia">

            <button type="submit">Guardar cambios</button>
        </form>
        <br>
        <a href="/observaciones">Volver</a>
    </div>
    """
    return html_base(contenido, user=user)

@app.post("/editar/{id_obs}")
async def editar_guardar(
    request: Request,
    id_obs: int,
    sucursal: str = Form(...),
    categoria: str = Form(...),
    prioridad: str = Form(...),
    comentario: str = Form(...),
    evidencia: UploadFile = File(None)
):
    user = requiere_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if categoria not in CATEGORIAS:
        categoria = "Otra"
    if prioridad not in PRIORIDADES:
        prioridad = "Media"

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("SELECT creado_por, evidencia_archivo, estado FROM observaciones WHERE id = ?", (id_obs,))
    obs = cursor.fetchone()

    if not obs:
        conn.close()
        return HTMLResponse(html_base("<div class='card'><h3>Observación no encontrada</h3><a href='/observaciones'>Volver</a></div>"))

    creado_por, evidencia_actual, estado_actual = obs
    puede_editar = user["rol"] in ["gerente"] or creado_por == user["nombre"]

    if not puede_editar:
        conn.close()
        return HTMLResponse(html_base("<div class='card'><h3>No tenés permiso para editar esta observación</h3><a href='/observaciones'>Volver</a></div>"))

    fecha_edicion = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    nueva_evidencia = guardar_evidencia(evidencia) or evidencia_actual

    cursor.execute("""
        UPDATE observaciones
        SET sucursal = ?, categoria = ?, prioridad = ?, comentario = ?, fecha_edicion = ?, editado_por = ?, evidencia_archivo = ?
        WHERE id = ?
    """, (sucursal, categoria, prioridad, comentario, fecha_edicion, user["nombre"], nueva_evidencia, id_obs))

    conn.commit()
    conn.close()

    notif_id = registrar_notificacion(
        usuario=user["nombre"],
        rol=user["rol"],
        estado=estado_actual,
        sucursal=sucursal,
        accion="Observación editada",
        observacion_id=id_obs,
    )

    await manager.broadcast_except({
        "type": "observation_event",
        "from": user["nombre"],
        "notification_id": notif_id,
        "title": APP_NOMBRE,
        "message": f"Observación editada · {user['nombre']} ({user['rol']}) · Estado: {estado_actual} · Sucursal: {sucursal}",
        "estado": estado_actual,
        "sucursal": sucursal,
        "prioridad": prioridad,
        "observacion_id": id_obs,
        "critical": prioridad == "Crítica",
    }, exclude_user=user["nombre"])

    return RedirectResponse(url="/observaciones", status_code=303)

@app.post("/resolver/{id_obs}")
async def resolver(request: Request, id_obs: int):
    user = requiere_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if user["rol"] not in ["gerente"]:
        return HTMLResponse(html_base("<div class='card'><h3>No tenés permiso para resolver observaciones</h3><a href='/observaciones'>Volver</a></div>"))

    fecha_edicion = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("SELECT sucursal FROM observaciones WHERE id = ?", (id_obs,))
    obs = cursor.fetchone()
    cursor.execute("""
        UPDATE observaciones
        SET estado = 'Resuelto', fecha_edicion = ?, editado_por = ?
        WHERE id = ?
    """, (fecha_edicion, user["nombre"], id_obs))
    conn.commit()
    conn.close()

    if obs:
        notif_id = registrar_notificacion(
            usuario=user["nombre"],
            rol=user["rol"],
            estado="Resuelto",
            sucursal=obs[0],
            accion="Observación resuelta",
            observacion_id=id_obs,
        )

        await manager.broadcast_except({
            "type": "observation_event",
            "from": user["nombre"],
            "notification_id": notif_id,
            "title": APP_NOMBRE,
            "message": f"Observación resuelta · {user['nombre']} ({user['rol']}) · Estado: Resuelto · Sucursal: {obs[0]}",
            "estado": "Resuelto",
            "sucursal": obs[0],
            "observacion_id": id_obs,
            "critical": False,
        }, exclude_user=user["nombre"])

    return RedirectResponse(url="/observaciones", status_code=303)

@app.get("/chat/{id_obs}", response_class=HTMLResponse)
def chat_observacion(request: Request, id_obs: int):
    user = requiere_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, sucursal, supervisor, categoria, prioridad, comentario, estado, fecha_creacion, fecha_edicion, creado_por, editado_por, evidencia_archivo
        FROM observaciones
        WHERE id = ?
    """, (id_obs,))
    obs = cursor.fetchone()

    if not obs:
        conn.close()
        return HTMLResponse(html_base("<div class='card'><h3>Observación no encontrada</h3><a href='/observaciones'>Volver</a></div>"))

    cursor.execute("""
        SELECT usuario, rol, mensaje, fecha
        FROM respuestas
        WHERE observacion_id = ?
        ORDER BY id ASC
    """, (id_obs,))
    respuestas = cursor.fetchall()
    conn.close()

    id_, sucursal, supervisor, categoria, prioridad, comentario, estado, fecha_creacion, fecha_edicion, creado_por, editado_por, evidencia_archivo = obs
    clase_estado = "resuelto" if estado == "Resuelto" else "pendiente"
    prioridad_clase = prioridad.lower().replace("í", "i")
    evidencia_html = f"<p><b>Evidencia:</b></p>{evidencia_preview_html(evidencia_archivo, 'Ampliar evidencia')}" if evidencia_archivo else ""

    mensajes_html = f"""
    <div class="card">
        <h3>Observación original</h3>
        <p><b>Sucursal:</b> {esc(sucursal)}</p>
        <p><b>Supervisor:</b> {esc(supervisor)}</p>
        <p><b>Categoría:</b> <span class="tag">{esc(categoria)}</span></p>
        <p><b>Prioridad:</b> <span class="prioridad-{prioridad_clase}">{esc(prioridad)}</span></p>
        <p><b>Fecha:</b> {esc(fecha_creacion)}</p>
        <p><b>Estado:</b> <span class="{clase_estado}">{esc(estado)}</span></p>
        <p>{esc(comentario)}</p>
        {evidencia_html}
        <p><small>Última edición: {esc(fecha_edicion or "Sin edición")} | Editado por: {esc(editado_por or "")}</small></p>
    </div>
    """

    for usuario, rol, mensaje, fecha in respuestas:
        clase = "mensaje-alto" if rol in ["gerente"] else "mensaje-supervisor"
        mensajes_html += f"""
        <div class="card mensaje {clase}">
            <p><b>{esc(usuario)}</b> ({esc(rol)}) - {esc(fecha)}</p>
            <p>{esc(mensaje)}</p>
        </div>
        """

    contenido = f"""
    <div class="card">
        <h2>Conversación de observación #{id_obs}</h2>
        <p>Usuario: <b>{esc(user['nombre'])}</b> | Rol: <b>{esc(user['rol'])}</b></p>
        <a href="/observaciones">Volver a observaciones</a>
    </div>

    {mensajes_html}

    <div class="card">
        <h3>Responder</h3>
        <form action="/responder/{id_obs}" method="post">
            <textarea name="mensaje" rows="4" required></textarea>
            <button type="submit">Enviar respuesta</button>
        </form>
    </div>
    """
    return html_base(contenido, user=user)

@app.post("/responder/{id_obs}")
async def responder_observacion(request: Request, id_obs: int, mensaje: str = Form(...)):
    user = requiere_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    fecha = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("SELECT id, sucursal, estado FROM observaciones WHERE id = ?", (id_obs,))
    obs = cursor.fetchone()

    if not obs:
        conn.close()
        return HTMLResponse(html_base("<div class='card'><h3>Observación no encontrada</h3><a href='/observaciones'>Volver</a></div>"))

    cursor.execute("""
        INSERT INTO respuestas (observacion_id, usuario, rol, mensaje, fecha)
        VALUES (?, ?, ?, ?, ?)
    """, (id_obs, user["nombre"], user["rol"], mensaje, fecha))

    conn.commit()
    conn.close()

    notif_id = registrar_notificacion(
        usuario=user["nombre"],
        rol=user["rol"],
        estado=obs[2],
        sucursal=obs[1],
        accion="Nueva respuesta",
        observacion_id=id_obs,
    )

    payload_msg = guardar_chat_mensaje(
        remitente=user["nombre"],
        remitente_rol=user["rol"],
        destinatario=None,
        mensaje=mensaje,
        tipo="observacion",
        observacion_id=id_obs,
        sucursal=obs[1],
        prioridad=None,
    )

    await manager.broadcast({
        "type": "chat_message",
        "message": payload_msg
    })

    await manager.broadcast_except({
        "type": "observation_event",
        "from": user["nombre"],
        "notification_id": notif_id,
        "title": APP_NOMBRE,
        "message": f"Nueva respuesta · {user['nombre']} ({user['rol']}) · Estado: {obs[2]} · Sucursal: {obs[1]}",
        "estado": obs[2],
        "sucursal": obs[1],
        "observacion_id": id_obs,
        "critical": False,
    }, exclude_user=user["nombre"])

    return RedirectResponse(url=f"/chat/{id_obs}", status_code=303)

# ============================================================
# EJECUCIÓN EN VS CODE
# ============================================================
# Opción recomendada desde la terminal:
#   python -m uvicorn main:app --host 0.0.0.0 --port 8000
#
# También podés ejecutar este archivo con el botón Run de VS Code.
# En ese caso se usa el bloque siguiente.

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
