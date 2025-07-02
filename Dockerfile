# Stage 1: Builder
FROM python:3.11-slim AS builder

# Install Chromium and related dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-common \
    libnss3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/ein-automation
COPY ein-automation/requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Stage 2: Final runtime image
FROM python:3.11-slim

ENV CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Install Chromium, Selenium dependencies, and additional libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    libnss3 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxi6 \
    libxrandr2 \
    libxss1 \
    libxtst6 \
    libgbm1 \
    libxshmfence1 \
    libasound2 \
    fonts-liberation \
    fonts-freefont-ttf \
    libjpeg62-turbo \
    libopenjp2-7 \
    libfreetype6 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/ein-automation
COPY --from=builder /usr/local /usr/local
COPY ein-automation/ .

EXPOSE 8000
RUN useradd -m appuser && chown -R appuser /app
USER appuser
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "120", "--timeout-graceful-shutdown", "30"]