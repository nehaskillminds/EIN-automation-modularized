from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, ElementNotInteractableException,
    WebDriverException, StaleElementReferenceException)
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains
import psutil
import logging

logger = logging.getLogger(__name__)

# Function to initialize the webdriver
def initialize_driver(self):

    try:
        self.log_system_resources()
        options = Options()

            # Set Chromium binary explicitly
        options.binary_location = "/usr/bin/chromium"

            # Enable verbose logging to log file
        options.add_argument('--log-level=ALL')
        options.add_argument(f'--log-path={self.driver_log_path}')

            # Headless + AKS-safe Chromium config
        options.add_argument('--headless=new')  # Modern headless mode
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--remote-debugging-port=9222')
        options.add_argument('--remote-debugging-address=0.0.0.0')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
            # Optional: for more stability inside containers
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-infobars')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--start-maximized')

            # Configure logging capabilities
        options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

            # Point to chromedriver binary explicitly
        service = ChromeService(
            executable_path="/usr/bin/chromedriver",  # NOT /usr/bin/chromium
            log_path=self.driver_log_path,
            service_args=["--verbose"]
        )

            # Start WebDriver
        self.driver = webdriver.Chrome(
            service=service,
            options=options,

        )

        self.wait = WebDriverWait(self.driver, self.timeout)

            # Override default JS alert/confirm/prompt behavior
        self.driver.execute_script("""
            window.alert = function() { return true; };
            window.confirm = function() { return true; };
            window.prompt = function() { return null; };
            window.open = function() { return null; };
        """)

        logger.info("WebDriver initialized successfully with Chromium")
    except Exception as e:
        logger.error(f"Failed to initialize WebDriver: {str(e)}")
        raise

# Function to capture the browser logs at every step 
def capture_browser_logs(self):
    """Capture Chrome DevTools console logs."""
    try:
        if self.driver:
            logs = self.driver.get_log("browser")
            self.console_logs.extend(logs)
            for log in logs:
                logger.debug(f"Browser console: {log['level']} - {log['message']}")
    except Exception as e:
        logger.warning(f"Failed to capture browser logs: {str(e)}")

# Function to log system resources used 
def log_system_resources(self):
    """Log CPU and memory usage."""
    try:
        process = psutil.Process()
        memory = process.memory_info().rss / 1024 / 1024  # MB
        cpu_percent = psutil.cpu_percent(interval=0.1)
        logger.debug(f"System resources: Memory={memory:.2f}MB, CPU={cpu_percent:.1f}%")
    except Exception as e:
        logger.warning(f"Failed to log system resources: {str(e)}")