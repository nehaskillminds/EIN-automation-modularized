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


# Pydantic models for data validation

class ThirdPartyDesignee(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None
    authorized: Optional[str] = None

class EmployeeDetails(BaseModel):
    other: Optional[str] = None

class LLCDetails(BaseModel):
    number_of_members: Optional[str] = None

class CaseData(BaseModel):
    record_id: str
    form_type: Optional[str] = None
    entity_name: Optional[str] = None
    entity_type: Optional[str] = None
    formation_date: Optional[str] = None
    business_category: Optional[str] = None
    business_description: Optional[str] = None
    business_address_1: Optional[str] = None
    entity_state: Optional[str] = None
    business_address_2: Optional[str] = None
    city: Optional[str] = None
    zip_code: Optional[str] = None
    quarter_of_first_payroll: Optional[str] = None
    entity_state_record_state: Optional[str] = None
    case_contact_name: Optional[str] = None
    ssn_decrypted: Optional[str] = None
    proceed_flag: Optional[str] = "true"
    entity_members: Optional[Dict[str, str]] = None
    locations: Optional[List[Dict[str, Any]]] = None
    mailing_address: Optional[Dict[str, str]] = None
    county: Optional[str] = None
    trade_name: Optional[str] = None
    care_of_name: Optional[str] = None
    closing_month: Optional[str] = None
    filing_requirement: Optional[str] = None
    employee_details: Optional[EmployeeDetails] = None
    third_party_designee: Optional[ThirdPartyDesignee] = None
    llc_details: Optional[LLCDetails] = None