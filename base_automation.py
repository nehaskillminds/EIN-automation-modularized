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

class FormAutomationBase:
    """Reusable base class for web form automation"""
    
    def __init__(self, headless: bool = False, timeout: int = 300, keep_browser_open: bool = True):
        self.timeout = timeout
        # self.headless = headless

        self.keep_browser_open = keep_browser_open

        self.driver = None
        self.wait = None

    
    def fill_field(self, locator: Tuple[str, str], value: str, label: str = "field"):
        """Fill a form field with error handling"""
        if not value or not value.strip():
            logger.warning(f"Skipping {label} - empty value")
            return False
        
        try:
            field = self.wait.until(EC.element_to_be_clickable(locator))
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", field)
            field.clear()
            field.send_keys(str(value))
            logger.info(f"Filled {label}: {value}")
            return True
        except Exception as e:
            logger.warning(f"Failed to fill {label}: {e}")
            return False
    
    def click_button(self, locator: Tuple[str, str], desc: str = "button", retries: int = 3) -> bool:
        """Click a button with enhanced retry logic and multiple strategies"""
        for attempt in range(retries + 1):
            try:
                element = self.wait.until(EC.presence_of_element_located(locator))
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.5)
                clickable_element = self.wait.until(EC.element_to_be_clickable(locator))
                click_strategies = [
                    lambda: clickable_element.click(),
                    lambda: self.driver.execute_script("arguments[0].click();", clickable_element),
                    lambda: ActionChains(self.driver).move_to_element(clickable_element).click().perform()
                ]
                for strategy in click_strategies:
                    try:
                        strategy()
                        logger.info(f"Clicked {desc}")
                        time.sleep(1)
                        return True
                    except Exception as click_error:
                        if strategy == click_strategies[-1]:
                            raise click_error
                        continue
            except Exception as e:
                if attempt == retries:
                    logger.warning(f"Failed to click {desc} after {retries + 1} attempts: {e}")
                    return False
                logger.warning(f"Click attempt {attempt + 1} failed for {desc}: {e}, retrying...")
                time.sleep(1)
        return False
    
    def select_radio(self, radio_id: str, desc: str = "radio") -> bool:
        """Select radio button with enhanced reliability"""
        try:
            radio = self.wait.until(EC.element_to_be_clickable((By.ID, radio_id)))
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", radio)
            if self.driver.execute_script(f"document.getElementById('{radio_id}').checked = true; return document.getElementById('{radio_id}').checked;"):
                logger.info(f"Selected {desc} via JavaScript")
                return True
            radio.click()
            logger.info(f"Selected {desc} via click")
            return True
        except Exception as e:
            logger.warning(f"Failed to select {desc} (ID: {radio_id}): {e}")
            return False
    
    def select_dropdown(self, locator: Tuple[str, str], value: str, label: str = "dropdown") -> bool:
        """Select dropdown option"""
        try:
            element = self.wait.until(EC.element_to_be_clickable(locator))
            select = Select(element)
            select.select_by_value(value)
            logger.info(f"Selected {label}: {value}")
            return True
        except Exception as e:
            logger.warning(f"Failed to select {label}: {e}")
            return False
    
    async def capture_page_as_pdf(self, data) -> Tuple[Optional[str], bool]:
        """Capture page as PDF, upload to Azure, and notify Salesforce."""
        try:
            print_params = {
                "printBackground": True,
                "preferCSSPageSize": True,
                "marginTop": 0,
                "marginBottom": 0,
                "marginLeft": 0,
                "marginRight": 0,
                "paperWidth": 8.27,
                "paperHeight": 11.69,
                "landscape": False
            }

            pdf_data = self.driver.execute_cdp_cmd("Page.printToPDF", print_params)
            pdf_bytes = base64.b64decode(pdf_data["data"])

            clean_name = re.sub(r"[^\w]", "", data.entity_name or "UnknownEntity")
            blob_name = f"EntityProcess/{data.record_id}/{clean_name}-ID-EINConfirmation.pdf"

            blob_url = self._upload_bytes_to_blob(pdf_bytes, blob_name, "application/pdf")

            # Notify Salesforce here
            if not self.confirmation_uploaded:
                await self.notify_screenshot_upload_to_salesforce(
                    entity_process_id=data.record_id,
                    blob_url=blob_url,
                    entity_name=data.entity_name or "UnknownEntity"
                )
                self.confirmation_uploaded = True


            return blob_url, True
        except Exception as e:
            logger.error(f"capture_page_as_pdf failed: {e}")
            return None
        
    def clear_and_fill(self, by_locator: Tuple[str, str], value: str, description: str):
        try:
            field = self.wait.until(EC.element_to_be_clickable(by_locator))
            field.clear()
            field.send_keys(value)
            logger.info(f"Cleared and filled {description} with value: {value}")
        except Exception as e:
            self.capture_browser_logs()
            logger.error(f"Failed to clear and fill {description}: {str(e)}")
            raise AutomationError(f"Failed to clear and fill {description}", details=str(e))
    

    def cleanup(self):
        """Clean up browser resources, virtual display, and logs with robust error handling."""
        if self.keep_browser_open:
            logger.info("Skipping browser cleanup because keep_browser_open=True")
            return
        
        try:
            if hasattr(self, 'driver') and self.driver:
                self.capture_browser_logs()
                self.driver.quit()
                logger.info("Browser closed successfully")
        except WebDriverException as e:
            logger.warning(f"Error closing browser: {str(e)}")
            try:
                self.driver.service.process.kill()
                logger.warning("Force-killed browser process")
            except Exception as e:
                logger.error(f"Failed to force-kill browser process: {str(e)}")
        finally:
            self.driver = None

            if hasattr(self, 'driver_log_path') and os.path.exists(self.driver_log_path):
                try:
                    os.remove(self.driver_log_path)
                    logger.debug(f"Removed ChromeDriver log file: {self.driver_log_path}")
                except Exception as e:
                    logger.error(f"Failed to remove ChromeDriver log: {str(e)}")