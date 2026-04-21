import os
import asyncio
import uvicorn

from fastapi import FastAPI, Security, HTTPException, status
from fastapi.security import APIKeyHeader
from playwright.async_api import async_playwright

app = FastAPI()

API_KEY_NAME = "x-api-key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
ACTUAL_API_KEY = os.getenv("API_KEY")

SCRAPE_SEMAPHORE = asyncio.Semaphore(1)

ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-infobars",
    "--ignore-certificate-errors",
    "--disable-gpu",
    "--disable-dev-shm-usage",
]

async def get_api_key(api_key_header_value: str = Security(api_key_header)):
    if not ACTUAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error de configuración: API_KEY no encontrada en variables de entorno."
        )

    if api_key_header_value == ACTUAL_API_KEY:
        return api_key_header_value

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No autorizado: API Key inválida o faltante"
    )

@app.get("/", dependencies=[Security(get_api_key)])
async def obtener_divisas():
    url = "https://www.banorte.com/Indicadores/"

    async with SCRAPE_SEMAPHORE:
        try:
            print(f"🌍 Consultando {url}...", flush=True)

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=ARGS,
                )

                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1920, "height": 1080},
                    locale="es-MX",
                )

                page = await context.new_page()

                await page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )

                await page.goto(
                    url,
                    timeout=90000,
                    wait_until="domcontentloaded",
                )

                # Espera la tabla real, no un id viejo
                await page.wait_for_selector(
                    "table.table-indicators tbody tr",
                    state="attached",
                    timeout=45000,
                )

                rows = page.locator("table.table-indicators tbody tr")
                row_count = await rows.count()

                venta = None
                compra = None

                for i in range(row_count):
                    row = rows.nth(i)
                    cols = row.locator("td")
                    cols_count = await cols.count()

                    # Solo filas de datos: nombre, compra, venta
                    if cols_count == 3:
                        nombre = (await cols.nth(0).inner_text()).strip().upper()
                        if nombre == "VENTANILLA":
                            compra = (await cols.nth(1).inner_text()).strip()
                            venta = (await cols.nth(2).inner_text()).strip()
                            break

                if not venta:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="No se encontró la fila VENTANILLA o la columna de venta."
                    )

                return {
                    "tipo-cambio-compra-banorte": compra,
                    "tipo-cambio-venta-banorte": venta
                }

        except HTTPException:
            raise
        except Exception as e:
            print(f"❌ Error en scraper: {e}", flush=True)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Error consultando Banorte: {str(e)}"
            )