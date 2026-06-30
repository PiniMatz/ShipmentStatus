import os
import logging
import requests
import hashlib
import re
import time
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Map internal carrier names to WhereParcel carrier codes
CARRIER_MAPPING = {
    "UPS": "us.ups",
    "USPS": "us.usps",
    "FedEx": "us.fedex",
    "DHL": "global.dhl",
    "Cainiao": "global.cainiao",
    "China Post": "cn.chinapost"
}

def get_mock_status(tracking_number):
    """
    Generate realistic mock tracking info based on the tracking number.
    Helps during development or if API keys are not supplied.
    """
    if not tracking_number:
        return "Unknown", "No tracking number available"
        
    # Use hash of tracking number to keep it deterministic but seemingly random
    h = int(hashlib.md5(tracking_number.encode('utf-8')).hexdigest(), 16)
    states = ["Info Received", "In Transit", "Out for Delivery", "Delivered"]
    details = [
        "Shipment information received by carrier.",
        "Parcel is in transit. Left facility.",
        "Parcel is out for delivery with local courier.",
        "Delivered. Package left at front door/mailbox."
    ]
    
    idx = h % len(states)
    return states[idx], details[idx]

def get_cainiao_status(tracking_number):
    """
    Fetch real tracking updates directly and for free from Cainiao's public web endpoint.
    Cainiao handles AliExpress shipping and aggregates status for many global postal handovers.
    """
    url = f"https://global.cainiao.com/global/detail.json?mailNos={tracking_number}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://global.cainiao.com/"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("module"):
                module_data = data["module"][0]
                detail_list = module_data.get("detailList", [])
                
                if detail_list:
                    # The first item is usually the most recent event
                    latest_event = detail_list[0]
                    desc = latest_event.get("desc", "No description available")
                    stand_code = latest_event.get("standdCode", "").upper()
                    
                    status = "In Transit"
                    if "DELIVERED" in stand_code or "SIGN" in stand_code or "SUCCESS" in stand_code:
                        status = "Delivered"
                    elif "OUT_FOR_DELIVERY" in stand_code or "DELIVERYING" in stand_code:
                        status = "Out for Delivery"
                    elif "PICKUP" in stand_code or "WAIT_FOR_PICKUP" in stand_code:
                        status = "Out for Delivery"
                        
                    return {
                        "status": status,
                        "details": desc,
                        "provider": "cainiao (direct)"
                    }
    except Exception as e:
        logger.error(f"Error querying Cainiao: {e}")
        
    return None

def get_selenium_israelpost(tracking_number):
    """
    Track package using headless Selenium directly from Israel Post.
    Resolves Radware bot challenges automatically using real browser automation.
    """
    # Import locally to avoid requiring Selenium if not used
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from webdriver_manager.chrome import ChromeDriverManager
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = None
    try:
        logger.info(f"Starting Chrome to scrape Israel Post status for: {tracking_number}")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Remove webdriver signature to bypass protection
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "const newProto = navigator.__proto__; delete newProto.webdriver; navigator.__proto__ = newProto;"
        })
        
        url = f"https://doar.israelpost.co.il/en/deliverytracking?itemcode={tracking_number}"
        driver.get(url)
        
        # Wait for Search button to become clickable
        search_button = WebDriverWait(driver, 8).until(
            lambda d: d.find_element(By.XPATH, "//button[contains(., 'Search')] | //span[contains(text(), 'Search')]/..")
        )
        time.sleep(1)
        search_button.click()
        
        # Wait dynamically for timeline/results list to populate
        WebDriverWait(driver, 10).until(
            lambda d: "locality" in d.find_element(By.TAG_NAME, "body").text.lower() or 
                      "useful actions" in d.find_element(By.TAG_NAME, "body").text.lower() or 
                      "date" in d.find_element(By.TAG_NAME, "body").text.lower()
        )
        
        body_text = driver.find_element(By.TAG_NAME, "body").text
        driver.quit()
        
        lines = [line.strip() for line in body_text.split('\n') if line.strip()]
        
        status_desc = "Notification received regarding shipment"
        status_state = "In Transit"
        
        for i, line in enumerate(lines):
            # Locate date marker (dd/mm/yyyy)
            if re.match(r'^\d{2}/\d{2}/\d{4}$', line):
                candidates = []
                if i + 1 < len(lines):
                    candidates.append(lines[i+1])
                if i + 2 < len(lines):
                    candidates.append(lines[i+2])
                status_desc = " | ".join(candidates)
                break
                
        lower_desc = status_desc.lower()
        if "delivered" in lower_desc:
            status_state = "Delivered"
        elif "out for delivery" in lower_desc or "distribution" in lower_desc:
            status_state = "Out for Delivery"
            
        return {
            "status": status_state,
            "details": status_desc,
            "provider": "israelpost (selenium)"
        }
    except Exception as e:
        if driver:
            driver.quit()
        logger.error(f"Israel Post Selenium tracking error: {e}")
        return None

def get_selenium_aramex(tracking_number):
    """
    Track package using headless Selenium directly from Aramex tracking portal.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from webdriver_manager.chrome import ChromeDriverManager
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = None
    try:
        logger.info(f"Starting Chrome to scrape Aramex status for: {tracking_number}")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Bypass signature
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "const newProto = navigator.__proto__; delete newProto.webdriver; navigator.__proto__ = newProto;"
        })
        
        url = "https://www.aramex.com/ae/en/track/shipments"
        driver.get(url)
        
        textarea = WebDriverWait(driver, 8).until(
            lambda d: d.find_element(By.ID, "TrackingCardsNumber")
        )
        textarea.clear()
        textarea.send_keys(tracking_number)
        
        # Click search via JavaScript to avoid overlaps/popups blocking clicks
        btn = driver.find_element(By.ID, "btn-trackresult-tracksubmit")
        driver.execute_script("arguments[0].click();", btn)
        
        # Wait dynamically for latest update card to load
        WebDriverWait(driver, 10).until(
            lambda d: "latest update" in d.find_element(By.TAG_NAME, "body").text.lower()
        )
        
        body_text = driver.find_element(By.TAG_NAME, "body").text
        driver.quit()
        
        lines = [line.strip() for line in body_text.split('\n') if line.strip()]
        
        status_desc = "Shipment in transit"
        status_state = "In Transit"
        
        for i, line in enumerate(lines):
            if "latest update" in line.lower():
                candidates = []
                if i + 1 < len(lines):
                    candidates.append(lines[i+1])
                if i + 2 < len(lines):
                    candidates.append(lines[i+2])
                status_desc = " - ".join(candidates)
                break
                
        lower_desc = status_desc.lower()
        if "delivered" in lower_desc:
            status_state = "Delivered"
        elif "out for delivery" in lower_desc:
            status_state = "Out for Delivery"
            
        return {
            "status": status_state,
            "details": status_desc,
            "provider": "aramex (selenium)"
        }
    except Exception as e:
        if driver:
            driver.quit()
        logger.error(f"Aramex Selenium tracking error: {e}")
        return None

def get_tracking_status(tracking_number, carrier_name):
    """
    Fetch tracking status.
    First tries 17track API if token is configured in .env.
    Otherwise tries free, direct carrier fetch (Cainiao/Postal),
    then falls back to WhereParcel API if configured,
    and finally falls back to simulated Mock status.
    """
    if not tracking_number:
        return {
            "status": "Unknown",
            "details": "No tracking number provided.",
            "provider": "none"
        }

    carrier_lower = str(carrier_name).lower()
    tracking_lower = str(tracking_number).lower()

    # 1. Try 17track API if token is configured in .env (highly recommended for Israel Post, Aramex, etc.)
    token17 = os.getenv("17TRACK_API_KEY") or os.getenv("TRACK17_API_KEY")
    if token17 and token17 != "PASTE_YOUR_17TRACK_TOKEN_HERE":
        logger.info(f"Querying 17track API for: {tracking_number}")
        url = "https://api.17track.net/track/v2.2/getRealTimeTrackInfo"
        headers = {
            "17token": token17,
            "Content-Type": "application/json"
        }
        payload = [{"number": tracking_number, "carrier": 0}]
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                res_data = response.json()
                if res_data.get("code") == 0:
                    data = res_data.get("data", {})
                    accepted = data.get("accepted", [])
                    if accepted:
                        item = accepted[0]
                        track_info = item.get("track_info", {})
                        api_status = track_info.get("status", "").lower()
                        latest_event = track_info.get("latest_event", {})
                        desc = latest_event.get("description") or latest_event.get("desc") or "No description available"
                        
                        status = "In Transit"
                        if api_status == "delivered":
                            status = "Delivered"
                        elif api_status == "pickup":
                            status = "Out for Delivery"
                        elif api_status == "notfound":
                            status = "Info Received"
                            
                        return {
                            "status": status,
                            "details": desc,
                            "provider": "17track"
                        }
                    else:
                        rejected = data.get("rejected", [])
                        if rejected:
                            err_msg = rejected[0].get("error", {}).get("message", "Rejected by 17track")
                            logger.warning(f"17track rejected tracking number {tracking_number}: {err_msg}")
                else:
                    logger.error(f"17track API returned error code {res_data.get('code')}: {res_data.get('data')}")
            else:
                logger.error(f"17track HTTP status {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"17track connection error: {e}")

    # 2. Keyless Local Selenium Scraper for Israel Post & Aramex (No API key required)
    is_israel_post = "israel" in carrier_lower or "postal" in carrier_lower or tracking_lower.endswith("il") or tracking_lower.startswith("ru")
    is_aramex = "aramex" in carrier_lower or len(tracking_number) == 10 and tracking_number.isdigit()
    
    if is_israel_post:
        logger.info(f"Using local Selenium scraper for Israel Post: {tracking_number}")
        res = get_selenium_israelpost(tracking_number)
        if res:
            return res
            
    if is_aramex:
        logger.info(f"Using local Selenium scraper for Aramex: {tracking_number}")
        res = get_selenium_aramex(tracking_number)
        if res:
            return res

    # 3. Try free direct Cainiao lookup
    logger.info(f"Trying direct Cainiao fetch for tracking: {tracking_number}")
    cainiao_info = get_cainiao_status(tracking_number)
    if cainiao_info:
        return cainiao_info

    # 4. Try configured WhereParcel API (if active in .env)
    provider = os.getenv("TRACKING_PROVIDER", "mock").lower()
    if provider == "whereparcel":
        api_key = os.getenv("WHEREPARCEL_API_KEY")
        secret_key = os.getenv("WHEREPARCEL_SECRET_KEY")
        
        if api_key and secret_key:
            carrier_code = CARRIER_MAPPING.get(carrier_name, "auto")
            url = "https://api.whereparcel.com/v2/track"
            headers = {
                "Authorization": f"Bearer {api_key}:{secret_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "trackingNumber": tracking_number
            }
            if carrier_code != "auto":
                payload["carrier"] = carrier_code
                
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    tracking_info = data.get("tracking", data)
                    status = tracking_info.get("status", "In Transit")
                    detail = tracking_info.get("lastEvent", {}).get("description", "In transit to destination")
                    return {
                        "status": status,
                        "details": detail,
                        "provider": "whereparcel"
                    }
            except Exception as e:
                logger.error(f"WhereParcel connection error: {e}")

    # 5. Fallback: Simulated Mock Status
    status, detail = get_mock_status(tracking_number)
    return {
        "status": status,
        "details": f"[Simulated Status] {detail}",
        "provider": "mock"
    }
