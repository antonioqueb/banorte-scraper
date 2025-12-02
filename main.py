import uvicorn
import os
from fastapi import FastAPI, Security, HTTPException, status
from fastapi.security import APIKeyHeader
from playwright.async_api import async_playwright
import asyncio

app = FastAPI()

# --- CONFIGURACIÓN DE SEGURIDAD (.env) ---
# 1. Define el header que vas a buscar (x-api-key)
API_KEY_NAME = "x-api-key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# 2. Carga la clave real desde el entorno (inyectada por docker desde .env)
ACTUAL_API_KEY = os.getenv("API_KEY")

# 3. Función de validación que se ejecuta antes del endpoint
async def get_api_key(api_key_header: str = Security(api_key_header)):
    # Seguridad extra: Si no configuraste el .env, bloquea todo por seguridad
    if not ACTUAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error de configuración: API_KEY no encontrada en variables de entorno."
        )

    if api_key_header == ACTUAL_API_KEY:
        return api_key_header
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No autorizado: API Key inválida o faltante"
    )

# --- CONFIGURACIÓN PLAYWRIGHT (Stealth) ---
ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-infobars",
    "--ignore-certificate-errors",
    "--disable-gpu",
    "--disable-dev-shm-usage"
]

# --- ENDPOINT PROTEGIDO ---
# dependencies=[Security(get_api_key)] obliga a pasar la validación
@app.get("/", dependencies=[Security(get_api_key)])
async def obtener_divisas():
    url = "https://www.banorte.com/wps/portal/banorte/Home/indicadores/dolares-y-divisas"
    
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True, args=ARGS)
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="es-MX"
            )
            
            page = await context.new_page()
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            # Navegar
            print(f"🌍 Consultando {url}...", flush=True)
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            
            # Esperar existencia del elemento
            await page.wait_for_selector("#dolarVenta", state="attached", timeout=30000)
            
            # Esperar a que el texto NO esté vacío (lógica anti-vacío)
            await page.wait_for_function("""
                () => {
                    const el = document.querySelector('#dolarVenta');
                    return el && el.innerText.trim().length > 0;
                }
            """, timeout=15000)

            # Extraer solo lo que necesitamos
            venta = await page.inner_text("#dolarVenta")
            
            await browser.close()
            
            # Validación final
            if not venta:
                 return {"error": "No se pudo obtener el valor"}

            # Respuesta limpia solicitada
            return {
                "tipo-cambio-venta-banorte": venta.strip()
            }

        except Exception as e:
            print(f"❌ Error: {e}", flush=True)
            return {"error": str(e)}

if __name__ == "__main__":
    # Inicia el servidor
    uvicorn.run(app, host="0.0.0.0", port=8000)