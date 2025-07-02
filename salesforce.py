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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

access_token: Optional[str] = None
instance_url: Optional[str] = None

# Get salesforce access token for authentication
async def get_salesforce_access_token() -> Tuple[Optional[str], Optional[str]]:
    """Retrieve Salesforce access token and instance URL using OAuth password grant, based on provided curl format."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                 # url="https://login.salesforce.com/services/oauth2/token",
                url="https://test.salesforce.com/services/oauth2/token",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json"
                    
                },
                data={
                    "grant_type": "password",
                    "client_id": CONFIG["SALESFORCE_CLIENT_ID"],
                    "client_secret": CONFIG["SALESFORCE_CLIENT_SECRET"],
                    "username": CONFIG["SALESFORCE_USERNAME"],
                    "password": CONFIG["SALESFORCE_PASSWORD"] 
                }
            )
            response.raise_for_status()
            data = response.json()
            access_token = data.get("access_token")
            instance_url = data.get("instance_url")
            if not access_token or not instance_url:
                logger.error(f"Missing access_token or instance_url in Salesforce response: {data}")
                return None, None
            logger.info(f"Successfully retrieved Salesforce access token. Instance URL: {instance_url}")
            return access_token, instance_url

    except httpx.HTTPStatusError as e:
        logger.error(f"Salesforce token request failed: {e.response.status_code} - {e.response.text}")
        return None, None
    except Exception as e:
        logger.error(f"Error retrieving Salesforce token: {str(e)}")
        return None, None
    
# Initialize the salesforce authentication by getting the token    
async def initialize_salesforce_auth(self):
    """Initialize Salesforce authentication."""
    self.access_token, self.instance_url = await get_salesforce_access_token()
    if not self.access_token or not self.instance_url:
        raise RuntimeError("Failed to obtain Salesforce access token")
    logger.info(f"Salesforce instance URL: {self.instance_url}")
    

# Send the EIN back to salesforce and leave error code empty
async def notify_salesforce_success(self, entity_process_id: str, ein_number: str):
    await self.initialize_salesforce_auth()  # ensures access_token is fresh

    url = f"{self.instance_url}/services/apexrest/service/v2/formautomation/ein/update?entityProcessId={entity_process_id}"

    headers = {
        "Authorization": f"Bearer {self.access_token}",
        "Content-Type": "application/json"
    }

    payload = {
     "entityProcessId": entity_process_id,
        "einNumber": ein_number,
        "errorCode": "",
        "status": "success"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)

        if response.status_code == 401:
            logger.warning("Salesforce token expired. Refreshing...")
            await self.initialize_salesforce_auth()
            headers["Authorization"] = f"Bearer {self.access_token}"
            response = await client.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            logger.error(f"Failed to notify Salesforce of EIN success: {response.status_code} - {response.text}")
        else:
            logger.info("Successfully notified Salesforce of EIN submission success.")


# Send the error code to salesforce and leave EIN empty
async def notify_salesforce_error_code(self, entity_process_id: str, error_code: str, status: str = "fail"):
    await self.initialize_salesforce_auth()
        
    payload = {
        "entityProcessId": entity_process_id,
        "einNumber": "",
        "errorCode": error_code,
        "status": status
    }

     # base_url = "https://corpnet.my.salesforce.com"  # use production
    base_url = "https://corpnet--fullphase2.sandbox.my.salesforce.com"  # uncomment for sandbox

    url = f"{base_url}/services/apexrest/service/v2/formautomation/ein/update?entityProcessId={entity_process_id}"

        
    headers = {
        "Authorization": f"Bearer {self.access_token}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"Notified Salesforce of EIN error code: {error_code}")

# Send the EIN Letter PDF to salesforce  Content_Migration__c endpoint 
async def notify_ein_letter_to_salesforce(self, entity_process_id: str, blob_url: str, entity_name: str):
    """Notify Salesforce of uploaded EINLetter.pdf (post-submission)."""
    try:
        await self.initialize_salesforce_auth()

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        clean_name = re.sub(r'\s+', '', entity_name)
        file_name = f"{clean_name}-ID-EINLetter"
        extension = "pdf"
        migration_id = f"{hash(blob_url)}_{int(time.time())}"

        payload = {
            "Name": f"{file_name}.pdf",
            "File_Extension__c": extension,
            "Migration_ID__c": migration_id,
            "File_Name__c": file_name,
            "Parent_Name__c": "EntityProcess",
            "Account_ID__c": "",
            "Case_ID__c": "",
            "Entity_ID__c": "",
            "Order_ID__c": "",
            "RFI_ID__c": "",
            "Entity_Process_Id__c": entity_process_id,
            "Blob_URL__c": blob_url,
            "Is_Content_Created__c": False,
            "Is_Errored__c": False,
            "Historical_Record__c": False,
            "Exclude_from_Partner_API__c": False,
            "Deleted_by_Client__c": False,
            "Hidden_From_Client__c": False  # important: this is False now
        }

        url = f"{self.instance_url}/services/data/v63.0/sobjects/Content_Migration__c/"
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info(f"Salesforce notified of EINLetter.pdf upload: {response.status_code}")
            return True
    except Exception as e:
        logger.error(f"Failed to notify Salesforce of EINLetter.pdf upload: {str(e)}")
        return False

# Send the confirmation PDF to salesforce Content_Migration__c endpoint
async def notify_screenshot_upload_to_salesforce(self, entity_process_id: str, blob_url: str, entity_name: str):
    """Notify Salesforce of uploaded EINConfirmation.pdf"""
    try:
        await self.initialize_salesforce_auth()

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        clean_name = re.sub(r'\s+', '', entity_name)
        file_name = f"{clean_name}-ID-EINConfirmation"
        extension = "pdf"
        migration_id = f"{hash(blob_url)}_{int(time.time())}"

        payload = {
            "Name": f"{file_name}.pdf",
            "File_Extension__c": extension,
            "Migration_ID__c": migration_id,
            "File_Name__c": file_name,
            "Parent_Name__c": "EntityProcess",
            "Account_ID__c": "",
            "Case_ID__c": "",
            "Entity_ID__c": "",
            "Order_ID__c": "",
            "RFI_ID__c": "",
            "Entity_Process_Id__c": entity_process_id,
            "Blob_URL__c": blob_url,
            "Is_Content_Created__c": False,
            "Is_Errored__c": False,
            "Historical_Record__c": False,
            "Exclude_from_Partner_API__c": False,
            "Deleted_by_Client__c": False,
            "Hidden_From_Client__c": True
        }

        url = f"{self.instance_url}/services/data/v59.0/sobjects/Content_Migration__c/"
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info(f"Salesforce notified of EINConfirmation upload: {response.status_code}")
            self.confirmation_uploaded = True
            return True
    except Exception as e:
        logger.error(f"Failed to notify Salesforce of screenshot upload: {str(e)}")
        return False