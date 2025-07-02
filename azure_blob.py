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

logger = logging.getLogger(__name__)


def _upload_bytes_to_blob(self, data_bytes: bytes, blob_name: str, content_type: str):
    """Upload bytes directly to Azure Blob Storage and set index tags."""
    try:
        connection_string = f"DefaultEndpointsProtocol=https;AccountName={CONFIG['AZURE_STORAGE_ACCOUNT_NAME']};AccountKey={CONFIG['AZURE_ACCESS_KEY']};EndpointSuffix=core.windows.net"
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        container_client = blob_service_client.get_container_client(CONFIG['AZURE_CONTAINER_NAME'])
            
            # Upload the blob first
        blob_client = container_client.upload_blob(
            name=blob_name,
            data=data_bytes,
            overwrite=True,
            content_type=content_type
         )
            
        # Set the blob index tags
        tags = {"HiddenFromClient": "true"}
        blob_client.set_blob_tags(tags)
            
        blob_url = f"https://{CONFIG['AZURE_STORAGE_ACCOUNT_NAME']}.blob.core.windows.net/{CONFIG['AZURE_CONTAINER_NAME']}/{blob_name}"
        logger.info(f"Uploaded to Azure Blob Storage with tags: {blob_url}")
        return blob_url
            
    except AzureError as e:
        logger.error(f"Azure upload failed: {e}")
        raise

def upload_log_to_blob(self, record_id: str) -> Optional[str]:
    """Upload ChromeDriver logs directly to Azure Blob Storage."""
    try:
        if not os.path.exists(self.driver_log_path):
            logger.warning(f"No log file found at {self.driver_log_path}")
            return None
                
        with open(self.driver_log_path, "rb") as f:
            log_data = f.read()
                
        blob_name = f"logs/{record_id}/chromedriver_{int(time.time())}.log"
        return self._upload_bytes_to_blob(log_data, blob_name, "text/plain")
            
    except Exception as e:
        logger.error(f"Failed to upload logs to Azure Blob: {e}")
        return None
    
def _save_json_data_sync(self, data: Dict[str, Any], case_data: CaseData = None, file_name: str = None):

    try:
        legal_name = data.get('entity_name')
        clean_legal_name = re.sub(r"[^\w]", "", legal_name or "UnknownEntity")

        # If no custom file name, default to EntityName_data.json
        if not file_name:
            file_name = f"{clean_legal_name}_data.json"

        blob_name = f"EntityProcess/{data['record_id']}/{file_name}"
        json_data = json.dumps(data, indent=2)

        connection_string = (
            f"DefaultEndpointsProtocol=https;"
            f"AccountName={CONFIG['AZURE_STORAGE_ACCOUNT_NAME']};"
            f"AccountKey={CONFIG['AZURE_ACCESS_KEY']};"
            f"EndpointSuffix=core.windows.net"
        )

        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        container_client = blob_service_client.get_container_client(CONFIG['AZURE_CONTAINER_NAME'])

        # Upload the blob
        blob_client = container_client.upload_blob(
            name=blob_name,
            data=json_data.encode('utf-8'),
            overwrite=True,
            content_type="application/json"
        )

            # Set blob tags
        tags = {"HiddenFromClient": "true"}
        blob_client.set_blob_tags(tags)

        blob_url = f"https://{CONFIG['AZURE_STORAGE_ACCOUNT_NAME']}.blob.core.windows.net/{CONFIG['AZURE_CONTAINER_NAME']}/{blob_name}"
        logger.info(f"JSON data uploaded with tags: {blob_url}")
        return True
    except Exception as e:
        logger.error(f"Failed to upload JSON data to Azure Blob: {e}")
        return False