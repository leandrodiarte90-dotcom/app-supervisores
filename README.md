# App Supervisores V2 Organizada

Versión organizada tomando como base `app_supervisores_mobile_first_CORREGIDO_V2.py`, que era la versión funcional y visualmente correcta.

## Estructura

- `main.py`: rutas FastAPI, lógica de negocio y renderizado HTML.
- `static/css/styles.css`: estilos Elegant Sport responsive.
- `static/js/app.js`: comportamiento mobile, tablas responsivas y preview de evidencias.
- `static/img/logo.png`: logo usado por la app.
- `evidencias_supervisores/`: imágenes o archivos cargados como evidencia.
- `exports_supervisores/`: exportaciones Excel generadas.

## Instalación

```powershell
python -m pip install -r requirements.txt
```

## Ejecutar

```powershell
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Abrir en PC:

```text
http://127.0.0.1:8000
```

En celular, usando la misma WiFi:

```text
http://IP_DE_TU_PC:8000
```

## Usuarios de prueba

Contraseña inicial: `1234`.

Usuarios: Carina, Diego, Norma, Luisa, Walter, Sebastian, Gaston.
