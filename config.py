import os
import json
import re
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
from fastapi import Header
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, ElementNotInteractableException,
    WebDriverException, StaleElementReferenceException)
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains
from pydantic import BaseModel
from typing import Optional, Dict, Tuple, List, Any
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2AuthorizationCodeBearer
from jose import jwt, JWTError
import httpx
import asyncio
from pyvirtualdisplay import Display

import base64
import fitz  # PyMuPDF
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from azure.core.exceptions import AzureError
from tenacity import retry, stop_after_attempt, wait_exponential
import traceback
import requests
import psutil  # For resource monitoring
from typing import Optional
import io
import logging

from dotenv import load_dotenv


def read_secret_from_file(secret_name):
    try:
        with open(f"/mnt/secrets-store/{secret_name}", "r") as f:
            return f.read().strip()
    except Exception:
        return None

def get_secret(name: str, default: str = None) -> Optional[str]:
    # Try Azure Key Vault
    try:
        secret = secret_client.get_secret(name)
        print(f"GET_SECRET (vault): {name} -> [retrieved]")
        return secret.value
    except Exception as e:
        print(f"GET_SECRET (vault failed): {name}, falling back. Error: {e}")

    # Try environment variable
    value = os.environ.get(name)
    if value:
        print(f"GET_SECRET (env): {name} -> {value}")
        return value

    # Try mounted file (fallback)
    value = read_secret_from_file(name)
    if value:
        print(f"GET_SECRET (file): {name} -> {value}")
        return value

    print(f"GET_SECRET (default): {name} -> {default}")
    return default


KEY_VAULT_NAME = "corpnet-formpal-keyvault"
KV_URI = f"https://{KEY_VAULT_NAME}.vault.azure.net"
credential = DefaultAzureCredential()
secret_client = SecretClient(vault_url=KV_URI, credential=credential)

# Dictionary to store environment variables
CONFIG = {
    'JSON_FILE_PATH': os.path.join(os.getcwd(), "salesforce_data.json"),
    'PORT': int(get_secret("PORT", "8000")),
    'BROWSER_TIMEOUT': int(get_secret("BROWSER-TIMEOUT", "300")),
    'ALLOW_UNAUTHENTICATED_SALESFORCE': str(get_secret("ALLOW-UNAUTHENTICATED-SALESFORCE", "false")).lower() == "true",
    'SALESFORCE_ENDPOINT': get_secret("SALESFORCE-ENDPOINT"),
    'SALESFORCE_CLIENT_ID': get_secret("SALESFORCE-CLIENT-ID"),
    'SALESFORCE_CLIENT_SECRET': get_secret("SALESFORCE-CLIENT-SECRET"),
    'SALESFORCE_USERNAME': get_secret("SALESFORCE-USERNAME"),
    'SALESFORCE_PASSWORD': get_secret("SALESFORCE-PASSWORD"),
    'SALESFORCE_TOKEN': get_secret("SALESFORCE-TOKEN"),
    'AZURE_STORAGE_ACCOUNT_NAME': get_secret("AZURE-STORAGE-ACCOUNT-NAME", "formfillscreenshots"),
    'AZURE_ACCESS_KEY': get_secret("AZURE-ACCESS-KEY"),
    'AZURE_CONTAINER_NAME': get_secret("AZURE-CONTAINER-NAME", "payload"),
    'TENANT_ID': get_secret("TENANT-ID"),
    'CLIENT_ID': get_secret("CLIENT-ID"),
    'CLIENT_SECRET': get_secret("CLIENT-SECRET"),
    'REDIRECT_URI': get_secret("REDIRECT-URI", "http://4.246.236.24/docs/oauth2-redirect"),
}

# Validate required secrets
required_secrets = [
    'TENANT_ID', 'CLIENT_ID', 'CLIENT_SECRET', 'AZURE_STORAGE_ACCOUNT_NAME', 'AZURE_ACCESS_KEY',
    'AZURE_CONTAINER_NAME', 'SALESFORCE_ENDPOINT', 'SALESFORCE_CLIENT_ID', 'SALESFORCE_CLIENT_SECRET',
    'SALESFORCE_USERNAME', 'SALESFORCE_PASSWORD', 'SALESFORCE_TOKEN'
]

# Check for missing secrets
missing_secrets = [var for var in required_secrets if not CONFIG.get(var)]
if missing_secrets:
    raise RuntimeError(f"Missing required configuration secrets: {', '.join(missing_secrets)}")