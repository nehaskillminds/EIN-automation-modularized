from .base_automation import FormAutomationBase
from .azure_blob import _upload_bytes_to_blob
from .salesforce import get_salesforce_access_token, notify_screenshot_upload_to_salesforce, notify_ein_letter_to_salesforce, notify_salesforce_success, notify_salesforce_error_code

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
from app.exceptions import AutomationError

logger = logging.getLogger(__name__)

class IRSEINAutomation(FormAutomationBase):

    STATE_MAPPING = {
        "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", 
        "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
        "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID",
        "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
        "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
        "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN", "MISSISSIPPI": "MS",
        "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
        "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY",
        "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK",
        "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
        "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT",
        "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
        "WISCONSIN": "WI", "WYOMING": "WY", "DISTRICT OF COLUMBIA": "DC"
    }
    
    ENTITY_TYPE_MAPPING = {
        "Sole Proprietorship": "Sole Proprietor",
        "Individual": "Sole Proprietor",
        "Partnership": "Partnership",
        "Joint venture": "Partnership",
        "Limited Partnership": "Partnership",
        "General partnership": "Partnership",
        "C-Corporation": "Corporations",
        "S-Corporation": "Corporations",
        "Professional Corporation": "Corporations",
        "Corporation": "Corporations",
        "Non-Profit Corporation": "View Additional Types, Including Tax-Exempt and Governmental Organizations",
        "Limited Liability": "Limited Liability Company (LLC)",
        "Company (LLC)": "Limited Liability Company (LLC)",
        "LLC": "Limited Liability Company (LLC)",
        "Limited Liability Company": "Limited Liability Company (LLC)",
        "Limited Liability Company (LLC)": "Limited Liability Company (LLC)",
        "Professional Limited Liability Company": "Limited Liability Company (LLC)",
        "Limited Liability Partnership": "Partnership",
        "LLP": "Partnership",
        "Professional Limited Liability Company (PLLC)": "Limited Liability Company (LLC)",
        "Association": "View Additional Types, Including Tax-Exempt and Governmental Organizations",
        "Co-ownership": "Partnership",
        "Doing Business As (DBA)": "Sole Proprietor",
        "Trusteeship": "Trusts"
    }
    
    RADIO_BUTTON_MAPPING = {
        "Sole Proprietor": "sole",
        "Partnership": "partnerships",
        "Corporations": "corporations",
        "Limited Liability Company (LLC)": "limited",
        "Estate": "estate",
        "Trusts": "trusts",
        "View Additional Types, Including Tax-Exempt and Governmental Organizations": "viewadditional"
    }
    
    SUB_TYPE_MAPPING = {
        "Sole Proprietorship": "Sole Proprietor",
        "Individual": "Sole Proprietor",
        "Partnership": "Partnership",
        "Joint venture": "Joint Venture",
        "Limited Partnership": "Partnership",
        "General partnership": "Partnership",
        "C-Corporation": "Corporation",
        "S-Corporation": "S Corporation",
        "Professional Corporation": "Personal Service Corporation",
        "Corporation": "Corporation",
        "Non-Profit Corporation": "**This is dependent on the business_description**",
        "Limited Liability": "N/A",
        "Limited Liability Company (LLC)": "N/A",
        "LLC": "N/A",
        "Limited Liability Company": "N/A",
        "Professional Limited Liability Company": "N/A",
        "Limited Liability Partnership": "Partnership",
        "LLP": "Partnership",
        "Professional Limited Liability Company (PLLC)": "N/A",
        "Association": "N/A",
        "Co-ownership": "Partnership",
        "Doing Business As (DBA)": "N/A",
        "Trusteeship": "Irrevocable Trust"
    }

    
    SUB_TYPE_BUTTON_MAPPING = {
        "Sole Proprietor": "sole",
        "Household Employer": "house",
        "Partnership": "parnership",
        "Joint Venture": "joint",
        "Corporation": "corp",
        "S Corporation": "scorp",
        "Personal Service Corporation": "personalservice",
        "Irrevocable Trust": "irrevocable",
        "Non-Profit/Tax-Exempt Organization": "nonprofit",
        "Other": "other_option"
    }

    async def final_submit(self, data: CaseData, json_data: dict) -> Tuple[Optional[str], Optional[str], bool]:
        einNumber = None
        pdf_azure_url = None

        try:
            # 1. Attempt to extract EIN using CSS selector
            ein_element = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "td[align='left'] > b"))
            )
            ein_text = ein_element.text.strip()

            if re.match(r"^\d{2}-\d{7}$", ein_text):
                einNumber = ein_text
                json_data["einNumber"] = einNumber
                logger.info(f"Extracted EIN: {einNumber}")
                self._save_json_data_sync(json_data)
            else:
                logger.warning(f"Extracted EIN '{ein_text}' does not match expected format XX-XXXXXXX")
        except Exception as e:
            logger.error(f"Failed to extract EIN: {e}")

        # 2. Check if failure screen is present
        try:
            page_text = self.driver.page_source.lower()
            if "we are unable to provide you with an ein" in page_text:
                logger.warning("EIN assignment failed. Capturing failure PDF and extracting reference number...")

                # Extract reference number
                ref_match = re.search(r"reference number\s+(\d+)", page_text)
                if ref_match:
                    reference_number = ref_match.group(1)
                    json_data["irs_reference_number"] = reference_number
                    logger.info(f"Extracted IRS Reference Number: {reference_number}")
                else:
                    logger.warning("Reference number not found on failure page.")

                # Generate failure PDF
                try:
                    clean_name = re.sub(r"[^\w]", "", data.entity_name or "UnknownEntity")
                    pdf_data = self.driver.execute_cdp_cmd("Page.printToPDF", {
                        "printBackground": True,
                        "preferCSSPageSize": True
                    })
                    pdf_bytes = base64.b64decode(pdf_data["data"])
                    blob_name = f"EntityProcess/{data.record_id}/{clean_name}-ID-EINSubmissionFailure.pdf"
                    pdf_azure_url = self._upload_bytes_to_blob(pdf_bytes, blob_name, "application/pdf")
                    logger.info(f"Failure PDF uploaded: {pdf_azure_url}")
                    if not confirmation_uploaded:
                        await self.notify_salesforce_error_code(
                        entity_process_id=data.record_id,
                        error_code=reference_number,
                        status="fail"
                        )

                except Exception as e:
                    logger.error(f"Failed to capture/upload failure PDF: {e}")

                # Save updated JSON
                try:
                    self._save_json_data_sync(json_data)
                    logger.info("Updated JSON with reference number saved.")
                except Exception as e:
                    logger.error(f"Failed to save JSON with reference number: {e}")

                return None, pdf_azure_url, False
        except Exception as e:
            logger.error(f"Failure page detection or handling failed: {e}")

        if einNumber:
            try:
                await self.notify_salesforce(
                    record_id=data.record_id,
                    status="success",
                    ein_number=einNumber
                )
            except Exception as e:
                logger.error(f"Failed to notify Salesforce: {e}")
                

        # 4. Download and upload EIN confirmation letter if EIN was found
        if einNumber:
            try:
                download_link = self.wait.until(EC.element_to_be_clickable((By.XPATH,"//a[contains(text(), 'EIN Confirmation Letter') and contains(@href, '.pdf')]")))

                pdf_url = download_link.get_attribute("href")

                # If relative path, add domain
                if pdf_url.startswith("/"):
                    pdf_url = "https://sa.www4.irs.gov" + pdf_url

                clean_name = re.sub(r'[^\w\-]', '', (data.entity_name or "UnknownEntity").replace(" ", ""))
                blob_name = f"EntityProcess/{data.record_id}/{clean_name}-ID-EINLetter.pdf"

                if pdf_url:
                    logger.info(f"Attempting direct download from URL: {pdf_url}")
                    response = requests.get(pdf_url)
                    if response.status_code == 200 and response.headers.get("Content-Type", "").startswith("application/pdf"):
                        pdf_bytes = response.content
                        pdf_azure_url = self._upload_bytes_to_blob(pdf_bytes, blob_name, "application/pdf")
                        logger.info(f"PDF uploaded to Azure Blob Storage: {pdf_azure_url}")
                        await self.notify_ein_letter_to_salesforce(
                            entity_process_id=data.record_id,
                            blob_url=pdf_azure_url,
                            entity_name=data.entity_name or "UnknownEntity"
                        )

                    else:
                        logger.warning(f"Unexpected PDF response: {response.status_code}, {response.headers.get('Content-Type')}")
                        raise Exception("Failed to download EIN confirmation letter.")
                else:
                    raise Exception("PDF href not found on page.")
            except Exception as e:
                logger.error(f"Failed to download or upload PDF: {e}")

        if not einNumber:
            try:
                # Upload failure screenshot as PDF to Azure
                clean_name = re.sub(r"[^\w]", "", data.entity_name or "UnknownEntity")
                pdf_data = self.driver.execute_cdp_cmd("Page.printToPDF", {
                    "printBackground": True,
                    "preferCSSPageSize": True
                })
                pdf_bytes = base64.b64decode(pdf_data["data"])
                blob_name = f"EntityProcess/{data.record_id}/{clean_name}-ID-EINSubmissionFailure.pdf"
                pdf_url = self._upload_bytes_to_blob(pdf_bytes, blob_name, "application/pdf")

                # Send to Content_Migration__c (same as Type 1/2)
                if not self.confirmation_uploaded:
                    await self.notify_screenshot_upload_to_salesforce(
                    entity_process_id=data.record_id,
                    blob_url=pdf_url,
                    entity_name=data.entity_name or "UnknownEntity"
                    )

                # Send EIN update (500 is generic error code)
                await self.notify_salesforce_error_code(
                    entity_process_id=data.record_id,
                    error_code="500"
                )
            except Exception as e:
                logger.error(f"Failed to handle generic failure notification: {e}")



        return einNumber, pdf_azure_url, einNumber is not None 
 

# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++


    async def handle_trusteeship_entity(self, data: CaseData):
        logger.info("Handling Trusteeship entity type form flow")
        defaults = self._get_defaults(data)

        try:
            self.log_system_resources()
            logger.info(f"Navigating to IRS EIN form for record_id: {data.record_id}")
            self.driver.set_page_load_timeout(self.timeout)
            self.driver.get("https://sa.www4.irs.gov/modiein/individual/index.jsp")
            logger.info("Navigated to IRS EIN form")
            
            # Handle potential alert popup
            try:
                self.driver.set_page_load_timeout(self.timeout)
                alert = WebDriverWait(self.driver, 5).until(EC.alert_is_present())
                alert_text = alert.text
                alert.accept()
                logger.info(f"Handled alert popup: {alert_text}")
            except TimeoutException:
                logger.debug("No alert popup appeared")

            # Wait for page to load
            try:
                self.driver.set_page_load_timeout(self.timeout)
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//input[@type='submit' and @name='submit' and @value='Begin Application >>']"))
                )
                logger.info("Page loaded successfully")
            except TimeoutException:
                self.capture_browser_logs()
                page_source = self.driver.page_source[:1000] if self.driver else "N/A"
                logger.error(f"Page load timeout. Current URL: {self.driver.current_url if self.driver else 'N/A'}, Page source: {page_source}")
                raise AutomationError("Page load timeout", details="Failed to locate Begin Application button")

            # Click Begin Application
            if not self.click_button((By.XPATH, "//input[@type='submit' and @name='submit' and @value='Begin Application >>']"), "Begin Application"):
                self.capture_browser_logs()
                raise AutomationError("Failed to click Begin Application", details="Button click unsuccessful after retries")

            # Wait for main form content
            try:
                self.driver.set_page_load_timeout(self.timeout)
                self.wait.until(EC.presence_of_element_located((By.ID, "individual-leftcontent")))
                logger.info("Main form content loaded")
            except TimeoutException:
                self.capture_browser_logs()
                raise AutomationError("Failed to load main form content", details="Element 'individual-leftcontent' not found")
            
            # Step 1: Select type and subtype
            entity_type = (data.entity_type or '').strip()
            mapped_type = self.ENTITY_TYPE_MAPPING.get(entity_type, "Trusts")
            logger.info(f"Mapped entity type: {entity_type} -> {mapped_type}")
            radio_id = self.RADIO_BUTTON_MAPPING.get(mapped_type)
            if not radio_id or not self.select_radio(radio_id, f"Entity type: {mapped_type}"):
                raise AutomationError("Failed to select Trusteeship entity type")

            self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue after entity type")

            sub_type = self.SUB_TYPE_MAPPING.get(entity_type, "Other")
            sub_radio_id = self.SUB_TYPE_BUTTON_MAPPING.get(sub_type, "other_option")
            if not self.select_radio(sub_radio_id, f"Sub-type: {sub_type}"):
                raise AutomationError("Failed to select Trusteeship sub-type")

            self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue after sub-type")
            self.capture_browser_logs()
            self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue after sub-type")
            self.capture_browser_logs()

            # Step 2: Fill name and SSN without clicking I Am Sole
            self.fill_field((By.XPATH, "//input[@id='responsiblePartyFirstName']"), defaults["first_name"], "Responsible First Name")
            self.capture_browser_logs()

            if defaults["middle_name"]:
                self.fill_field((By.XPATH, "//input[@id='responsiblePartyMiddleName']"), defaults["middle_name"], "Responsible Middle Name")
                self.capture_browser_logs()

            self.fill_field((By.XPATH, "//input[@id='responsiblePartyLastName']"), defaults["last_name"], "Responsible Last Name")
            self.capture_browser_logs()

            ssn = defaults["ssn_decrypted"].replace("-", "")
            self.fill_field((By.XPATH, "//input[@id='responsiblePartySSN3']"), ssn[:3], "SSN First 3")
            self.capture_browser_logs()
            self.fill_field((By.XPATH, "//input[@id='responsiblePartySSN2']"), ssn[3:5], "SSN Middle 2")
            self.capture_browser_logs()
            self.fill_field((By.XPATH, "//input[@id='responsiblePartySSN4']"), ssn[5:], "SSN Last 4")
            self.capture_browser_logs()

            self.click_button((By.XPATH, "//input[@type='submit' and @name='Submit2' and contains(@value, 'Continue >>')]"), "Continue after SSN")
            self.capture_browser_logs()

            # Step 3: Re-enter name fields after clearing
            self.clear_and_fill((By.XPATH, "//input[@id='responsiblePartyFirstName']"), defaults["first_name"], "Clear & Fill First Name")
            self.capture_browser_logs()
            if defaults["middle_name"]:
                self.fill_field((By.XPATH, "//input[@id='responsiblePartyMiddleName']"), defaults["middle_name"], "Responsible Middle Name")
                self.capture_browser_logs()
            self.clear_and_fill((By.XPATH, "//input[@id='responsiblePartyLastName']"), defaults["last_name"], "Clear & Fill Last Name")
            self.capture_browser_logs()

            # Step 4: Click I Am Sole radio and Continue
            self.select_radio("iamsole", "I Am Sole")
            self.capture_browser_logs()
            self.click_button((By.XPATH, "//input[@type='submit' and @name='Submit' and contains(@value, 'Continue >>')]"), "Continue after I Am Sole")
            self.capture_browser_logs()

            # Step 5: Fill mailing address
            
            
            mailing_address = data.mailing_address or {}
            self.fill_field((By.XPATH, "//input[@id='mailingAddressStreet']"), mailing_address.get("mailingStreet", ""), "Mailing Street")
            self.capture_browser_logs()
            self.fill_field((By.XPATH, "//input[@id='mailingAddressCity']"), mailing_address.get("mailingCity", ""), "Mailing City")
            self.capture_browser_logs()
            self.fill_field((By.XPATH, "//input[@id='mailingAddressState']"), mailing_address.get("mailingState", ""), "Mailing State")
            self.capture_browser_logs()
            self.fill_field((By.XPATH, "//input[@id='mailingAddressPostalCode']"), mailing_address.get("mailingZip", ""), "Zip")
            self.capture_browser_logs()

            self.fill_field((By.XPATH, "//input[@id='internationalPhoneNumber']"), defaults["phone"], "Phone Number")
            self.capture_browser_logs()

            self.click_button((By.XPATH, "//input[@type='submit' and @name='Submit' and contains(@value, 'Continue >>')]"), "Continue after Mailing")
            self.capture_browser_logs()

            try: 
                short_wait = WebDriverWait(self.driver, 20)  # ⏱ 5-second timeout instead of full default
                element = short_wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @name='Submit' and @value='Accept As Entered']")))
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                element.click()
                logger.info("Clicked Accept As Entered")
            except TimeoutException:
                logger.info("Accept As Entered button not found within 5 seconds, proceeding.")
            except Exception as e:
                logger.warning(f"Unexpected error while clicking Accept As Entered: {str(e)}")

            # Step 6: Fill business info
            try:
                business_name = defaults["entity_name"]

                # Clean and normalize name
                business_name = business_name.strip()
                business_name = re.sub(r'[^\w\s\-&]', '', business_name)  # Remove unwanted special characters

                # Remove common entity suffixes for Trusteeship
                suffixes = ['Corp', 'Inc', 'LLC', 'LC', 'PLLC', 'PA', 'L.L.C.', 'INC.', 'CORPORATION', 'LIMITED']
                pattern = r'\b(?:' + '|'.join(re.escape(suffix) for suffix in suffixes) + r')\b\.?$'
                business_name = re.sub(pattern, '', business_name, flags=re.IGNORECASE).strip()

            except Exception as e:
                logger.error(f"Failed to process business name: {str(e)}")
                business_name = defaults["entity_name"]

            try:
                filled = self.fill_field((By.ID, "businessOperationalLegalName"), business_name, "Legal Business Name")

                if not filled:
                    logger.info("Failed to fill business name in appropriate field based on entity type")
            except (TimeoutException, NoSuchElementException) as e:
                logger.info(f"Business name field not found: {str(e)}")



                
            self.fill_field((By.XPATH, "//input[@id='businessOperationalCounty']"), data.entity_state, "County")
            self.capture_browser_logs()

            state_select = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//select[@id='businessOperationalState']")))
            self.capture_browser_logs()
            Select(state_select).select_by_value(data.county[:2].upper())
            logger.info(f"Selected state: {data.county[:2].upper()}")
            self.capture_browser_logs()

            month, year = self.parse_formation_date(data.formation_date)
            if not self.select_dropdown((By.ID, "BUSINESS_OPERATIONAL_MONTH_ID"), str(month), "Formation Month"):
                self.capture_browser_logs()
                raise AutomationError("Failed to select Formation Month")
            if not self.fill_field((By.ID, "BUSINESS_OPERATIONAL_YEAR_ID"), str(year), "Formation Year"):
                self.capture_browser_logs()
                raise AutomationError("Failed to fill Formation Year")

            
            # Step 7: Continue, then no employees, then receive letter online
            self.click_button((By.XPATH, "//input[@type='submit' and @name='Submit' and contains(@value, 'Continue >>')]"), "Continue after Business Info")
            self.capture_browser_logs()
            for radio in [
                "radioHasEmployees_n",
            ]:
                if not self.select_radio(radio, radio):
                    self.capture_browser_logs()
                    raise AutomationError(f"Failed to select {radio}")
            if not self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue"):
                self.capture_browser_logs()
                raise AutomationError("Failed to continue after activity options")
            

            if not self.select_radio("receiveonline", "Receive Online"):
                self.capture_browser_logs()
                raise AutomationError("Failed to select Receive Online")

            # Proceed only if continue is successful
            if self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue after receive EIN"):
                self.capture_browser_logs()

                # ✅ TAKE CONFIRMATION SCREENSHOT ONLY NOW
                blob_url, success = await self.capture_page_as_pdf(data)
                logger.info(f"Confirmation screenshot uploaded to Azure: {blob_url}")
            else:
                raise Exception("Failed to continue after receive EIN selection")
            logger.info("Form filled successfully")


        except (TimeoutException, NoSuchElementException, ElementNotInteractableException, StaleElementReferenceException) as e:
            self.capture_browser_logs()
            page_source = self.driver.page_source[:1000] if self.driver else "N/A"
            logger.error(f"Form filling error at URL: {self.driver.current_url if self.driver else 'N/A'}, Error: {str(e)}, Page source: {page_source}")
            raise AutomationError("Form filling error", details=str(e))
        except WebDriverException as e:
            self.capture_browser_logs()
            if os.path.exists(self.driver_log_path):
                try:
                    with open(self.driver_log_path, 'r') as f:
                        driver_logs = f.read()
                        logger.error(f"ChromeDriver logs: {driver_logs}")
                except Exception as log_error:
                    logger.error(f"Failed to read ChromeDriver logs: {str(log_error)}")
            page_source = self.driver.page_source[:1000] if self.driver else "N/A"
            logger.error(f"WebDriver error during form filling at URL: {self.driver.current_url if self.driver else 'N/A'}, Error: {str(e)}, Page source: {page_source}")
            raise AutomationError("WebDriver error", details=str(e))
        except Exception as e:
            self.capture_browser_logs()
            page_source = self.driver.page_source[:1000] if self.driver else "N/A"
            logger.error(f"Unexpected error during form filling at URL: {self.driver.current_url if self.driver else 'N/A'}, Error: {str(e)}, Page source: {page_source}")
            
            try:
                handled = await self.detect_and_handle_type2_failure(data, json_data)
                if handled:
                    logger.warning("Handled as Type 2 EIN failure during form fill. Skipping exception raise.")
                    return  # Exit early, already handled
            except Exception as err:
                logger.error(f"Type 2 handler failed while processing EIN failure page: {err}")

            raise AutomationError("Unexpected form filling error", details=str(e))


            logger.info("Completed Trusteeship entity form successfully")

# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++trusteeship logic+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    
    async def navigate_and_fill_form(self, data: CaseData, json_data: dict):
        """Navigate and fill IRS EIN form with detailed error handling."""
        try:
            self.log_system_resources()
            logger.info(f"Navigating to IRS EIN form for record_id: {data.record_id}")
            self.driver.set_page_load_timeout(self.timeout)
            self.driver.get("https://sa.www4.irs.gov/modiein/individual/index.jsp")
            logger.info("Navigated to IRS EIN form")
            
            # Handle potential alert popup
            try:
                self.driver.set_page_load_timeout(self.timeout)
                alert = WebDriverWait(self.driver, 5).until(EC.alert_is_present())
                alert_text = alert.text
                alert.accept()
                logger.info(f"Handled alert popup: {alert_text}")
            except TimeoutException:
                logger.debug("No alert popup appeared")

            # Wait for page to load
            try:
                self.driver.set_page_load_timeout(self.timeout)
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//input[@type='submit' and @name='submit' and @value='Begin Application >>']"))
                )
                logger.info("Page loaded successfully")
            except TimeoutException:
                self.capture_browser_logs()
                page_source = self.driver.page_source[:1000] if self.driver else "N/A"
                logger.error(f"Page load timeout. Current URL: {self.driver.current_url if self.driver else 'N/A'}, Page source: {page_source}")
                raise AutomationError("Page load timeout", details="Failed to locate Begin Application button")

            # Click Begin Application
            if not self.click_button((By.XPATH, "//input[@type='submit' and @name='submit' and @value='Begin Application >>']"), "Begin Application"):
                self.capture_browser_logs()
                raise AutomationError("Failed to click Begin Application", details="Button click unsuccessful after retries")

            # Wait for main form content
            try:
                self.driver.set_page_load_timeout(self.timeout)
                self.wait.until(EC.presence_of_element_located((By.ID, "individual-leftcontent")))
                logger.info("Main form content loaded")
            except TimeoutException:
                self.capture_browser_logs()
                raise AutomationError("Failed to load main form content", details="Element 'individual-leftcontent' not found")

            # Select entity type
            entity_type = (data.entity_type or "").strip()
            mapped_type = self.ENTITY_TYPE_MAPPING.get(entity_type, "")
            radio_id = self.RADIO_BUTTON_MAPPING.get(mapped_type, "")
            if not radio_id or not self.select_radio(radio_id, f"Entity type: {mapped_type}"):
                self.capture_browser_logs()
                raise AutomationError(f"Failed to select entity type: {mapped_type}", details=f"Radio ID: {radio_id}")

            # Continue after entity type
            if not self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue"):
                self.capture_browser_logs()
                raise AutomationError("Failed to continue after entity type", details="Continue button click unsuccessful")

            # Handle sub-type selection
            if mapped_type not in ["Limited Liability Company (LLC)", "Estate"]:
                sub_type = self.SUB_TYPE_MAPPING.get(entity_type, "Other")
                if entity_type == "Non-Profit Corporation":
                    business_desc = (data.business_description or "").lower()
                    nonprofit_keywords = ["non-profit", "nonprofit", "charity", "charitable", "501(c)", "tax-exempt"]
                    sub_type = "Non-Profit/Tax-Exempt Organization" if any(keyword in business_desc for keyword in nonprofit_keywords) else "Other"
                sub_type_radio_id = self.SUB_TYPE_BUTTON_MAPPING.get(sub_type, "other_option")
                if not self.select_radio(sub_type_radio_id, f"Sub-type: {sub_type}"):
                    self.capture_browser_logs()
                    raise AutomationError(f"Failed to select sub-type: {sub_type}", details=f"Radio ID: {sub_type_radio_id}")
                if not self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue sub-type (first click)"):
                    self.capture_browser_logs()
                    raise AutomationError("Failed to continue after sub-type selection (first click)")
                time.sleep(0.5)
                if not self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue sub-type (second click)"):
                    self.capture_browser_logs()
                    raise AutomationError("Failed to continue after sub-type selection (second click)")
            else:
                if not self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue after entity type"):
                    self.capture_browser_logs()
                    raise AutomationError("Failed to continue after entity type")

            # Handle LLC-specific fields
            if mapped_type == "Limited Liability Company (LLC)":
                llc_members = 1
                if data.llc_details and data.llc_details.number_of_members is not None:
                    try:
                        llc_members = int(data.llc_details.number_of_members)
                        if llc_members < 1:
                            llc_members = 1
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Invalid LLC members value: {data.llc_details.number_of_members}, using default: 1")
                try:
                    self.driver.set_page_load_timeout(self.timeout)
                    field = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@id='numbermem' or @name='numbermem']")))
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", field)
                    field.clear()
                    time.sleep(0.2)
                    field.send_keys(str(llc_members))
                    logger.info(f"Filled LLC members: {llc_members}")
                except (TimeoutException, NoSuchElementException) as e:
                    self.capture_browser_logs()
                    raise AutomationError("Failed to fill LLC members", details=str(e))
                state_value = self.normalize_state(data.entity_state or data.entity_state_record_state)
                if not self.select_dropdown((By.ID, "state"), state_value, "State"):
                    self.capture_browser_logs()
                    raise AutomationError(f"Failed to select state: {state_value}")
                if not self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue"):
                    self.capture_browser_logs()
                    raise AutomationError("Failed to continue after LLC members and state")

            # Handle specific states for LLC
            specific_states = {"AZ", "CA", "ID", "LA", "NV", "NM", "TX", "WA", "WI"}
            if mapped_type == "Limited Liability Company (LLC)" and state_value in specific_states:
                if not self.select_radio("radio_n", "Non-partnership LLC option"):
                    self.capture_browser_logs()
                    raise AutomationError("Failed to select non-partnership LLC option")
                if not self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue after radio_n"):
                    self.capture_browser_logs()
                    raise AutomationError("Failed to continue after non-partnership LLC option")
                if not self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue after confirmation"):
                    self.capture_browser_logs()
                    raise AutomationError("Failed to continue after confirmation")
            else:
                if not self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue after LLC"):
                    self.capture_browser_logs()
                    raise AutomationError("Failed to continue after LLC")

            # Select new business
            if not self.select_radio("newbiz", "New Business"):
                self.capture_browser_logs()
                raise AutomationError("Failed to select new business")
            if not self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue"):
                self.capture_browser_logs()
                raise AutomationError("Failed to continue after business purpose")

            # Fill responsible party details
            defaults = self._get_defaults(data)
            first_name = data.entity_members.get("first_name_1", defaults["first_name"]) if data.entity_members else defaults["first_name"]
            last_name = data.entity_members.get("last_name_1", defaults["last_name"]) if data.entity_members else defaults["last_name"]
            middle_name = data.entity_members.get("middle_name_1", defaults["middle_name"]) if data.entity_members else defaults["middle_name"]

            if data.entity_type in ["Sole Proprietorship", "Individual"]:

                first_name_filled = self.fill_field((By.ID, "applicantFirstName"), first_name, "First Name (Applicant)")
                if not first_name_filled:
                    self.capture_browser_logs()
                    raise AutomationError(f"Failed to fill First Name: {first_name}")
                
                if middle_name:
                    middle_name_filled = self.fill_field((By.ID, "applicantMiddleName"), middle_name, "Middle Name (Applicant)")
                    if not middle_name_filled:
                        self.capture_browser_logs()
                        raise AutomationError(f"Failed to fill Middle Name: {middle_name}")
                    

                
                last_name_filled = self.fill_field((By.ID, "applicantLastName"), last_name, "Last Name (Applicant)")
                if not last_name_filled:
                    self.capture_browser_logs()
                    raise AutomationError(f"Failed to fill Last Name: {last_name}")
                
                
            else:
                first_name_filled = self.fill_field((By.ID, "responsiblePartyFirstName"), first_name, "First Name")
                if not first_name_filled:
                    self.capture_browser_logs()
                    raise AutomationError(f"Failed to fill First Name: {first_name}")
                
                if middle_name:
                    middle_name_filled = self.fill_field((By.ID, "responsiblePartyMiddleName"), middle_name, "Middle Name (Applicant)")
                    if not middle_name_filled:
                        self.capture_browser_logs()
                        raise AutomationError(f"Failed to fill Middle Name: {middle_name}")
                
                last_name_filled = self.fill_field((By.ID, "responsiblePartyLastName"), last_name, "Last Name")
                if not last_name_filled:
                    self.capture_browser_logs()
                    raise AutomationError(f"Failed to fill Last Name: {last_name}")

            
            # Fill SSN
            ssn = defaults["ssn_decrypted"].replace("-", "")

            if data.entity_type in ["Sole Proprietorship", "Individual"]:
                ssn_first_filled = self.fill_field((By.ID, "applicantSSN3"), ssn[:3], "SSN First 3 (Applicant)")
                if not ssn_first_filled:
                    self.capture_browser_logs()
                    raise AutomationError("Failed to fill SSN First 3")

                ssn_middle_filled = self.fill_field((By.ID, "applicantSSN2"), ssn[3:5], "SSN Middle 2 (Applicant)")
                if not ssn_middle_filled:
                    self.capture_browser_logs()
                    raise AutomationError("Failed to fill SSN Middle 2")

                ssn_last_filled = self.fill_field((By.ID, "applicantSSN4"), ssn[5:], "SSN Last 4 (Applicant)")
                if not ssn_last_filled:
                    self.capture_browser_logs()
                    raise AutomationError("Failed to fill SSN Last 4")
            else:
                ssn_first_filled = self.fill_field((By.ID, "responsiblePartySSN3"), ssn[:3], "SSN First 3")
                if not ssn_first_filled:
                    self.capture_browser_logs()
                    raise AutomationError("Failed to fill SSN First 3")

                ssn_middle_filled = self.fill_field((By.ID, "responsiblePartySSN2"), ssn[3:5], "SSN Middle 2")
                if not ssn_middle_filled:
                    self.capture_browser_logs()
                    raise AutomationError("Failed to fill SSN Middle 2")

                ssn_last_filled = self.fill_field((By.ID, "responsiblePartySSN4"), ssn[5:], "SSN Last 4")
                if not ssn_last_filled:
                    self.capture_browser_logs()
                    raise AutomationError("Failed to fill SSN Last 4")
            

            # Select I Am Sole
            if not self.select_radio("iamsole", "I Am Sole"):
                self.capture_browser_logs()
                raise AutomationError("Failed to select I Am Sole")
            if not self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue"):
                self.capture_browser_logs()
                raise AutomationError("Failed to continue after responsible party")

            # Fill address details
            if not self.fill_field((By.ID, "physicalAddressStreet"), defaults["business_address_1"], "Street"):
                self.capture_browser_logs()
                raise AutomationError("Failed to fill Physical Street")
            if not self.fill_field((By.ID, "physicalAddressCity"), defaults["city"], "Physical City"):
                self.capture_browser_logs()
                raise AutomationError("Failed to fill Physical City")
            if not self.select_dropdown((By.ID, "physicalAddressState"), self.normalize_state(data.entity_state), "Physical State"):
                self.capture_browser_logs()
                raise AutomationError("Failed to select Physical State")
            if not self.fill_field((By.ID, "physicalAddressZipCode"), defaults["zip_code"], "Physical Zip"):
                self.capture_browser_logs()
                raise AutomationError("Failed to fill Physical Zip")

            # Fill phone number
            phone = defaults["phone"] or "2812173123"
            phone_clean = re.sub(r'\D', '', phone)
            if len(phone_clean) == 10:
                if not self.fill_field((By.ID, "phoneFirst3"), phone_clean[:3], "Phone First 3"):
                    self.capture_browser_logs()
                    raise AutomationError("Failed to fill Phone First 3")
                if not self.fill_field((By.ID, "phoneMiddle3"), phone_clean[3:6], "Phone Middle 3"):
                    self.capture_browser_logs()
                    raise AutomationError("Failed to fill Phone Middle 3")
                if not self.fill_field((By.ID, "phoneLast4"), phone_clean[6:], "Phone Last 4"):
                    self.capture_browser_logs()
                    raise AutomationError("Failed to fill Phone Last 4")

            # Fill care of name (optional)
            allowed_entity_types = ["C-Corporation", "S-Corporation", "Professional Corporation", "Corporation"]
            if data.care_of_name and data.entity_type in allowed_entity_types:
                try:
                    self.driver.set_page_load_timeout(self.timeout)
                    self.wait.until(EC.presence_of_element_located((By.ID, "physicalAddressCareofName")))
                    if not self.fill_field((By.ID, "physicalAddressCareofName"), data.care_of_name, "Physical Care of Name"):
                        logger.warning("Failed to fill Physical Care of Name, proceeding")
                except (TimeoutException, NoSuchElementException) as e:
                    logger.info(f"Physical Care of Name field not found: {str(e)}")

            # Handle mailing address
            mailing_address = data.mailing_address or {}
            has_mailing_address = bool(mailing_address.get("mailingStreet", "").strip())

            # Handle mailing address
            mailing_address = data.mailing_address or {}
            has_mailing_address = bool(mailing_address.get("mailingStreet", "").strip())
            
            if has_mailing_address:
                if not self.select_radio("radioAnotherAddress_y", "Address option (Yes)"):
                    self.capture_browser_logs()
                    raise AutomationError("Failed to select Address option (Yes)")
            else:
                if not self.select_radio("radioAnotherAddress_n", "Address option (No)"):
                    self.capture_browser_logs()
                    raise AutomationError("Failed to select Address option (No)")
            if not self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue after address option"):
                self.capture_browser_logs()
                raise AutomationError("Failed to continue after address option")

            # Accept as entered
            try:
                short_wait = WebDriverWait(self.driver, 20)  # ⏱ 5-second timeout instead of full default
                element = short_wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @name='Submit' and @value='Accept As Entered']")))
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                element.click()
                logger.info("Clicked Accept As Entered")
            except TimeoutException:
                logger.info("Accept As Entered button not found within 5 seconds, proceeding.")
            except Exception as e:
                logger.warning(f"Unexpected error while clicking Accept As Entered: {str(e)}")

            # Fill mailing address details
            if has_mailing_address:
                if not self.fill_field((By.ID, "mailingAddressStreet"), mailing_address.get("mailingStreet", ""), "Mailing Street"):
                    self.capture_browser_logs()
                    raise AutomationError("Failed to fill Mailing Street")
                if not self.fill_field((By.ID, "mailingAddressCity"), mailing_address.get("mailingCity", ""), "Mailing City"):
                    self.capture_browser_logs()
                    raise AutomationError("Failed to fill Mailing City")
                if not self.fill_field((By.ID, "mailingAddressState"), mailing_address.get("mailingState", ""), "Mailing State"):
                    self.capture_browser_logs()
                    raise AutomationError("Failed to select Mailing State")
                if not self.fill_field((By.ID, "mailingAddressPostalCode"), mailing_address.get("mailingZip", ""), "Zip"):
                    self.capture_browser_logs()
                    raise AutomationError("Failed to fill Mailing Zip")
                if not self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue after mailing address"):
                    self.capture_browser_logs()
                    raise AutomationError("Failed to continue after mailing address")
                
                try:
                    short_wait = WebDriverWait(self.driver, 20)  # ⏱ 5-second timeout instead of full default
                    element = short_wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @name='Submit' and @value='Accept As Entered']")))
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                    element.click()
                    logger.info("Clicked Accept As Entered")
                except TimeoutException:
                    logger.info("Accept As Entered button not found within 5 seconds, proceeding.")
                except Exception as e:
                    logger.warning(f"Unexpected error while clicking Accept As Entered: {str(e)}")

            SUFFIX_RULES_BY_GROUP = {
                "sole": ['LLC', 'LC', 'PLLC', 'PA', 'Corp', 'Inc'],
                "partnerships": ['Corp', 'LLC', 'PLLC', 'LC', 'Inc', 'PA'],
                "corporations": ['LLC', 'PLLC', 'LC'],
                "limited": ['Corp', 'Inc', 'PA'],  # LLCs
                "trusts": ['Corp', 'LLC', 'PLLC', 'LC', 'Inc', 'PA'],
                "estate": ['Corp', 'LLC', 'PLLC', 'LC', 'Inc', 'PA'],
                "viewadditional": []  
            }
            # Fill business name
            try:
                business_name = defaults["entity_name"].strip()
                original_name = business_name  # after strip

                # Fix: Use ENTITY_TYPE_MAPPING to resolve label correctly
                entity_type_label = (data.entity_type or "").strip()
                mapped_type = self.ENTITY_TYPE_MAPPING.get(entity_type_label, "").strip()
                entity_group = self.RADIO_BUTTON_MAPPING.get(mapped_type)

                if entity_group:
                    suffixes = SUFFIX_RULES_BY_GROUP.get(entity_group, [])
                    for suffix in suffixes:
                        # Match suffix at the end, ignoring punctuation or trailing spaces
                        if re.search(rf'\b{suffix}\s*$', business_name, flags=re.IGNORECASE):
                            business_name = re.sub(rf'\b{suffix}\s*$', '', business_name, flags=re.IGNORECASE).strip()
                            logger.info(f"Stripped suffix '{suffix}' from business name: '{original_name}' -> '{business_name}'")
                            break  # Only strip one suffix

                # Clean allowed characters only
                business_name = re.sub(r"[^\w\s\-&]", "", business_name)

            except Exception as e:
                logger.error(f"Failed to process business name: {str(e)}")
                business_name = defaults["entity_name"]



            # Fill the appropriate IRS input field
            try:
                if entity_group == "sole":
                    filled = self.fill_field(
                        (By.ID, "businessOperationalTradeName"),
                        business_name,
                        "Trade Name (Sole Prop/Individual)"
                    )
                else:
                    filled = self.fill_field(
                        (By.ID, "businessOperationalLegalName"),
                        business_name,
                        "Legal Business Name"
                    )

                if not filled:
                    logger.info("Failed to fill business name in appropriate field based on entity type group")
            except (TimeoutException, NoSuchElementException) as e:
                logger.info(f"Business name field not found: {str(e)}")


            # Fill county and state
            if not self.fill_field((By.ID, "businessOperationalCounty"), self.normalize_state(data.entity_state), "County"):
                self.capture_browser_logs()
                raise AutomationError("Failed to fill County")
            
            # Always fill businessOperationalState
            try:
                self.select_dropdown((By.ID, "businessOperationalState"), self.normalize_state(data.county), "Business Operational State")
            except (TimeoutException, NoSuchElementException) as e:
                logger.info(f"Business Operational State dropdown not found: {str(e)}")

            # Conditionally fill articalsFiledState for certain entity types
            if data.entity_type in [
                "C-Corporation",
                "S-Corporation",
                "Corporation",
                "Limited Liability Company",
                "Professional Limited Liability Company",
                "Limited Liability Company (LLC)",
                "Professional Limited Liability Company (PLLC)",
                "LLC",
                "Professional Corporation"
            ]:
                try:
                    self.select_dropdown((By.ID, "articalsFiledState"), self.normalize_state(data.county), "Articles Filed State")
                    logger.info("Selected Articles Filed State")
                except (TimeoutException, NoSuchElementException) as e:
                    logger.info(f"Articles Filed State dropdown not found: {str(e)}")


            # Fill trade name
            try:
                if data.trade_name:
                    trade_name = data.trade_name.strip()
                    original_trade = trade_name

                    # Resolve group based on ENTITY_TYPE_MAPPING
                    entity_type_label = (data.entity_type or "").strip()
                    mapped_type = self.ENTITY_TYPE_MAPPING.get(entity_type_label, "").strip()
                    entity_group = self.RADIO_BUTTON_MAPPING.get(mapped_type)

                    # Trade suffix rules
                    TRADE_SUFFIX_RULES_BY_GROUP = {
                        "sole":     ['LLC', 'LC', 'PLLC', 'PA', 'Corp', 'Inc'],
                        "partnerships": ['LLC', 'LC', 'PLLC', 'PA', 'Corp', 'Inc'],
                        "corporations": ['LLC', 'LC', 'PLLC', 'PA', 'Corp', 'Inc'],
                        "limited":  ['LLC', 'LC', 'PLLC', 'PA', 'Corp', 'Inc'],
                        "trusts":   ['LLC', 'LC', 'PLLC', 'PA', 'Corp', 'Inc'],
                        "estate":   ['LLC', 'LC', 'PLLC', 'PA', 'Corp', 'Inc'],
                        "viewadditional": []
                    }

                    def clean_trade_chars(name: str) -> str:
                        return re.sub(r"[^\w\s\-&]", "", name)

                    # Strip suffix if applicable
                    if entity_group:
                        for suffix in TRADE_SUFFIX_RULES_BY_GROUP.get(entity_group, []):
                            if re.search(rf'\b{suffix}\s*$', trade_name, flags=re.IGNORECASE):
                                trade_name = re.sub(rf'\b{suffix}\s*$', '', trade_name, flags=re.IGNORECASE).strip()
                                logger.info(f"Stripped suffix '{suffix}' from trade name: '{original_trade}' -> '{trade_name}'")
                                break  # Remove only the first matching suffix

                    # Final cleanup
                    trade_name = clean_trade_chars(trade_name)

                    if not self.fill_field((By.ID, "businessOperationalTradeName"), trade_name, "Trade Name"):
                        self.capture_browser_logs()
                        raise AutomationError("Failed to fill Trade Name")
            except Exception as e:
                logger.warning(f"Could not process or fill Trade Name: {e}")





            # Fill formation date
            month, year = self.parse_formation_date(data.formation_date)
            if not self.select_dropdown((By.ID, "BUSINESS_OPERATIONAL_MONTH_ID"), str(month), "Formation Month"):
                self.capture_browser_logs()
                raise AutomationError("Failed to select Formation Month")
            if not self.fill_field((By.ID, "BUSINESS_OPERATIONAL_YEAR_ID"), str(year), "Formation Year"):
                self.capture_browser_logs()
                raise AutomationError("Failed to fill Formation Year")

            # Fill closing month
            if data.closing_month:
                MONTH_MAPPING = {
                    "january": "JANUARY", "jan": "JANUARY", "1": "JANUARY",
                    "february": "FEBRUARY", "feb": "FEBRUARY", "2": "FEBRUARY",
                    "march": "MARCH", "mar": "MARCH", "3": "MARCH",
                    "april": "APRIL", "apr": "APRIL", "4": "APRIL",
                    "may": "MAY", "5": "MAY",
                    "june": "JUNE", "jun": "JUNE", "6": "JUNE",
                    "july": "JULY", "jul": "JULY", "7": "JULY",
                    "august": "AUGUST", "aug": "AUGUST", "8": "AUGUST",
                    "september": "SEPTEMBER", "sep": "SEPTEMBER", "9": "SEPTEMBER",
                    "october": "OCTOBER", "oct": "OCTOBER", "10": "OCTOBER",
                    "november": "NOVEMBER", "nov": "NOVEMBER", "11": "NOVEMBER",
                    "december": "DECEMBER", "dec": "DECEMBER", "12": "DECEMBER"
                }
                # Only fill fiscal month for specific entity types
                if data.entity_type in [
                    "Partnership",
                    "Joint venture",
                    "Limited Partnership",
                    "General partnership",
                    "C-Corporation",
                    "Limited Liability Partnership",
                    "LLP", 
                    "Corporation"
                ]:
                    normalized_month = MONTH_MAPPING.get(data.closing_month.lower().strip(), None)
                    if normalized_month:
                        retries = 2
                        for attempt in range(retries):
                            try:
                                self.driver.set_page_load_timeout(self.timeout)
                                dropdown = self.wait.until(EC.element_to_be_clickable((By.ID, "fiscalMonth")))
                                select = Select(dropdown)
                                select.select_by_visible_text(normalized_month)
                                logger.info(f"Selected Fiscal Month: {normalized_month}")
                                break
                            except (TimeoutException, NoSuchElementException, StaleElementReferenceException) as e:
                                if attempt < retries - 1:
                                    logger.warning(f"Attempt {attempt + 1} to select Fiscal Month failed: {str(e)}")
                                    time.sleep(1)
                                else:
                                    self.capture_browser_logs()
                                    raise AutomationError(f"Failed to select Fiscal Month {normalized_month}", details=str(e))
                    else:
                        logger.warning(f"Invalid closing_month: {data.closing_month}, skipping")
                else:
                    logger.info(f"Skipping fiscal month selection for entity_type: {data.entity_type}")


            # Continue after formation date
            if not self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue"):
                self.capture_browser_logs()
                raise AutomationError("Failed to continue after formation date")

            # Select activity options
            for radio in [
                "radioTrucking_n",
                "radioInvolveGambling_n",
                "radioExciseTax_n",
                "radioSellTobacco_n",
                "radioHasEmployees_n"
            ]:
                if not self.select_radio(radio, radio):
                    self.capture_browser_logs()
                    raise AutomationError(f"Failed to select {radio}")
            if not self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue"):
                self.capture_browser_logs()
                raise AutomationError("Failed to continue after activity options")

            # Select other activity
            if not self.select_radio("other", "Other activity"):
                self.capture_browser_logs()
                raise AutomationError("Failed to select Other activity")
            if not self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue"):
                self.capture_browser_logs()
                raise AutomationError("Failed to continue after primary activity")

            # Select other service
            if not self.select_radio("other", "Other service"):
                self.capture_browser_logs()
                raise AutomationError("Failed to select Other service")
            if not self.fill_field((By.ID, "pleasespecify"), defaults["business_description"], "Business Description"):
                self.capture_browser_logs()
                raise AutomationError("Failed to fill Business Description")
            if not self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue"):
                self.capture_browser_logs()
                raise AutomationError("Failed to continue after specify service")

            # Select receive online

            if not self.select_radio("receiveonline", "Receive Online"):
                self.capture_browser_logs()
                raise AutomationError("Failed to select Receive Online")

            # Proceed only if continue is successful
            if self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"), "Continue after receive EIN"):
                self.capture_browser_logs()

                # ✅ TAKE CONFIRMATION SCREENSHOT ONLY NOW
                blob_url, success = await self.capture_page_as_pdf(data)
                logger.info(f"Confirmation screenshot uploaded to Azure: {blob_url}")
            else:
                raise Exception("Failed to continue after receive EIN selection")



            
            logger.info("Form filled successfully")
        except (TimeoutException, NoSuchElementException, ElementNotInteractableException, StaleElementReferenceException) as e:
            self.capture_browser_logs()
            page_source = self.driver.page_source[:1000] if self.driver else "N/A"
            logger.error(f"Form filling error at URL: {self.driver.current_url if self.driver else 'N/A'}, Error: {str(e)}, Page source: {page_source}")
            raise AutomationError("Form filling error", details=str(e))
        except WebDriverException as e:
            self.capture_browser_logs()
            if os.path.exists(self.driver_log_path):
                try:
                    with open(self.driver_log_path, 'r') as f:
                        driver_logs = f.read()
                        logger.error(f"ChromeDriver logs: {driver_logs}")
                except Exception as log_error:
                    logger.error(f"Failed to read ChromeDriver logs: {str(log_error)}")
            page_source = self.driver.page_source[:1000] if self.driver else "N/A"
            logger.error(f"WebDriver error during form filling at URL: {self.driver.current_url if self.driver else 'N/A'}, Error: {str(e)}, Page source: {page_source}")
            raise AutomationError("WebDriver error", details=str(e))
        except Exception as e:
            self.capture_browser_logs()
            page_source = self.driver.page_source[:1000] if self.driver else "N/A"
            logger.error(f"Unexpected error during form filling at URL: {self.driver.current_url if self.driver else 'N/A'}, Error: {str(e)}, Page source: {page_source}")
            
            try:
                handled = await self.detect_and_handle_type2_failure(data, json_data)
                if handled:
                    logger.warning("Handled as Type 2 EIN failure during form fill. Skipping exception raise.")
                    return  # Exit early, already handled
            except Exception as err:
                logger.error(f"Type 2 handler failed while processing EIN failure page: {err}")

            raise AutomationError("Unexpected form filling error", details=str(e))
        
    def normalize_state(self, state: str) -> str:
        """Normalize state name to 2-letter abbreviation.
        Args:
            state: State name (full name or 2-letter abbreviation)
        Returns:
            2-letter state abbreviation or original string if not found
        Raises:
            ValueError: If input is empty or None
        """
        if not state or not state.strip():
            raise ValueError("State cannot be empty")
        
        state_clean = state.upper().strip()
        
        # Create reverse mapping for abbreviation to full name
        reverse_mapping = {v: k for k, v in self.STATE_MAPPING.items()}
        
        # Case 1: Already a valid abbreviation (e.g., "TX")
        if len(state_clean) == 2 and state_clean in self.STATE_MAPPING.values():
            return state_clean
        
        # Case 2: Full state name (e.g., "TEXAS")
        if state_clean in self.STATE_MAPPING:
            return self.STATE_MAPPING[state_clean]
        
        # Case 3: Mixed case full name that matches when uppercased (e.g., "Texas")
        for full_name, abbr in self.STATE_MAPPING.items():
            if state_clean == full_name.upper():
                return abbr
        
        # Case 4: Input is a valid abbreviation's full name (e.g., "TEXAS" for "TX")
        if state_clean in reverse_mapping:
            return state_clean
        
        # If no match found, return the original cleaned input
        return state_clean

    def parse_formation_date(self, date_str: str) -> Tuple[str, int]:
        if not date_str:
            return 
        formats = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"]
        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str.strip(), fmt)
                return str(parsed.month), parsed.year
            except ValueError:
                continue
        logger.warning(f"Invalid date format: {date_str}, using default date")
        return 

    async def run_automation(self, data: CaseData) -> Tuple[bool, str, Optional[str]]:
        """Run the automation process for EIN form filling."""
        json_data = {}
        ein_number = ""
        pdf_azure_url = None
        success = False

        try:
            await self.initialize_salesforce_auth()

            # Log missing fields
            missing_fields = [field_name for field_name in data.__dict__
                            if data.__dict__[field_name] is None and field_name != 'record_id']
            if missing_fields:
                logger.info(f"Missing fields detected (using defaults): {', '.join(missing_fields)}")

            # Construct JSON data for saving if needed
            json_data = {
                "record_id": data.record_id,
                "form_type": data.form_type,
                "entity_name": data.entity_name,
                "entity_type": data.entity_type,
                "formation_date": data.formation_date,
                "business_category": data.business_category,
                "business_description": data.business_description,
                "business_address_1": data.business_address_1,
                "entity_state": data.entity_state,
                "business_address_2": data.business_address_2,
                "city": data.city,
                "zip_code": data.zip_code,
                "quarter_of_first_payroll": data.quarter_of_first_payroll,
                "entity_state_record_state": data.entity_state_record_state,
                "case_contact_name": data.case_contact_name,
                "ssn_decrypted": data.ssn_decrypted,
                "proceed_flag": data.proceed_flag,
                "entity_members": data.entity_members,
                "locations": data.locations,
                "mailing_address": data.mailing_address,
                "county": data.county,
                "trade_name": data.trade_name,
                "care_of_name": data.care_of_name,
                "closing_month": data.closing_month,
                "filing_requirement": data.filing_requirement,
                "employee_details": dict(data.employee_details) if data.employee_details else None,
                "third_party_designee": dict(data.third_party_designee) if data.third_party_designee else None,
                "llc_details": dict(data.llc_details) if data.llc_details else None,
                "missing_fields": missing_fields if missing_fields else None,
                "response_status": None
            }

            # 1. Start browser session
            self.initialize_driver()

            # 2. Navigate and fill IRS form
            if data.entity_type == "Trusteeship":
               await self.handle_trusteeship_entity(data)
            else:
                await self.navigate_and_fill_form(data, json_data)

            # 3. Capture confirmation page and send to Azure
            # confirmation_blob_url = await self.capture_page_as_pdf(data)

            # 4. Notify Salesforce for confirmation letter
            if not self.confirmation_uploaded:
                await self.notify_screenshot_upload_to_salesforce(
                    data.record_id, confirmation_blob_url, data.entity_name
                )
                self.confirmation_uploaded = True

            # 5. Continue to EIN Letter
            # if not self.click_button((By.XPATH, "//input[@type='submit' and @value='Continue >>']"),
            #                         "Final Continue before EIN download"):
            #     raise Exception("Failed to click final Continue button before EIN")

            # 6. Download EINLetter PDF + extract EIN + notify Salesforce
            ein_number, pdf_azure_url, success = await self.final_submit(data, json_data)

            # Notify Salesforce of successful EIN generation
            if success and ein_number:
                await self.notify_salesforce_success(data.record_id, ein_number)

            return success, ein_number or "", pdf_azure_url

        except Exception as e:
            logger.exception("Automation failed")

            # ✅ NEW: capture failure page and upload with consistent blob name
            try:
                clean_name = re.sub(r"[^\w]", "", data.entity_name or "UnknownEntity")
                blob_name = f"EntityProcess/{data.record_id}/{clean_name}-ID-EINSubmissionFailure.pdf"

                pdf_data = self.driver.execute_cdp_cmd("Page.printToPDF", {
                    "printBackground": True,
                    "preferCSSPageSize": True
                })
                pdf_bytes = base64.b64decode(pdf_data["data"])

                blob_url = self._upload_bytes_to_blob(pdf_bytes, blob_name, "application/pdf")
                logger.info(f"Uploaded automation failure PDF to: {blob_url}")

                if not self.confirmation_uploaded:
                    await self.notify_screenshot_upload_to_salesforce(
                        entity_process_id=data.record_id,
                        blob_url=blob_url,
                        entity_name=data.entity_name or "UnknownEntity"
                    )
                    self.confirmation_uploaded = True


            except Exception as pdf_error:
                logger.warning(f"Failed to capture or upload failure PDF: {pdf_error}")

            return False, "", None


        finally:
            # Upload ChromeDriver logs (if any)
            try:
                log_url = self.upload_log_to_blob(data.record_id)
                if log_url:
                    logger.info(f"Uploaded Chrome log to: {log_url}")
            except Exception as log_error:
                logger.warning(f"Failed to upload Chrome logs: {log_error}")

            # Clean up browser resources
            self.cleanup()



    def _get_defaults(self, data: CaseData) -> Dict[str, Any]:
        # Safely normalize all strings in entity_members_dict
        raw_members = data.entity_members or {}

        entity_members_dict = {
            "first_name_1": (raw_members.get("first_name_1") or "").strip(),
            "last_name_1": (raw_members.get("last_name_1") or "").strip(),
            "middle_name_1": (raw_members.get("middle_name_1") or "").strip(),
            "phone_1": (raw_members.get("phone_1") or "").strip(),
        }

        mailing_address_dict = data.mailing_address or {}
        third_party_designee = data.third_party_designee or ThirdPartyDesignee()
        employee_details = data.employee_details or EmployeeDetails()
        llc_details = data.llc_details or LLCDetails()

        return {
            'first_name': entity_members_dict['first_name_1'],
            'last_name': entity_members_dict['last_name_1'],
            'middle_name': entity_members_dict['middle_name_1'],
            'phone': entity_members_dict['phone_1'],
            'ssn_decrypted': str(data.ssn_decrypted or ""),
            'entity_name': str(data.entity_name or ""),
            'business_address_1': str(data.business_address_1 or ""),
            'city': str(data.city or ""),
            'zip_code': str(data.zip_code or ""),
            'business_description': str(data.business_description or "Any and lawful business"),
            'formation_date': str(data.formation_date or ""),
            'county': str(data.county or ""),
            'trade_name': str(data.trade_name or ""),
            'care_of_name': str(data.care_of_name or ""),
            'mailing_address': mailing_address_dict,
            'closing_month': str(data.closing_month or ""),
            'filing_requirement': str(data.filing_requirement or ""),
            'employee_details': dict(employee_details) if employee_details else {},
            'third_party_details': dict(third_party_designee) if third_party_designee else {},
            'llc_details': dict(llc_details) if llc_details else {}
        }