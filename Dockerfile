# Usamos imagen oficial de Microsoft Playwright (Ubuntu Jammy + Python)
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Copiar dependencias
COPY requirements.txt .

# Instalar librerías de python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código
COPY main.py .

# Instalar navegadores (aunque la imagen base suele traerlos, aseguramos)
RUN playwright install chromium

# Comando por defecto
CMD ["python", "main.py"]
