import os
import asyncio
import uvicorn

from fastapi import FastAPI, Security, HTTPException, status
from fastapi.security import APIKeyHeader
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

app = FastAPI()

API_KEY_NAME = "x-api-key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
ACTUAL_API_KEY = os.getenv("API_KEY")

# Limita cuántos scrapers corren al mismo tiempo.
# Si quieres uno por uno, deja 1. Si quieres algo más flexible, usa 2.
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

async def get_api_key(api_key_header: str = Security(api_key_header)):
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

@app.get("/", dependencies=[Security(get_api_key)])
async def obtener_divisas():
    url = "https://www.banorte.com/wps/portal/banorte/Home/indicadores/dolares-y-divisas"

    browser: Browser | None = None
    context: BrowserContext | None = None
    page: Page | None = None

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
                    timeout=60000,
                    wait_until="domcontentloaded",
                )

                await page.wait_for_selector(
                    "#dolarVenta",
                    state="attached",
                    timeout=30000,
                )

                await page.wait_for_function(
                    """
                    () => {
                        const el = document.querySelector('#dolarVenta');
                        return el && el.innerText.trim().length > 0;
                    }
                    """,
                    timeout=15000,
                )

                venta = (await page.inner_text("#dolarVenta")).strip()

                if not venta:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="No se pudo obtener el valor de venta."
                    )

                return {
                    "tipo-cambio-venta-banorte": venta
                }

        except HTTPException:
            raise
        except Exception as e:
            print(f"❌ Error en scraper: {e}", flush=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error consultando Banorte: {str(e)}"
            )
        finally:
            # Cierra en orden inverso al de creación
            if page is not None:
                try:
                    await page.close()
                except Exception as e:
                    print(f"⚠️ Error cerrando page: {e}", flush=True)

            if context is not None:
                try:
                    await context.close()
                except Exception as e:
                    print(f"⚠️ Error cerrando context: {e}", flush=True)

            if browser is not None:
                try:
                    await browser.close()
                except Exception as e:
                    print(f"⚠️ Error cerrando browser: {e}", flush=True)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)