import os
import logging
import requests
import hashlib
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

def get_tracking_status(tracking_number, carrier_name):
    """
    Fetch tracking status.
    First tries free, direct carrier fetch (Cainiao/Postal), then falls back to WhereParcel API if configured,
    and finally falls back to simulated Mock status.
    """
    if not tracking_number:
        return {
            "status": "Unknown",
            "details": "No tracking number provided.",
            "provider": "none"
        }

    # 1. Try free direct Cainiao lookup first for all tracking codes
    logger.info(f"Trying direct Cainiao fetch for tracking: {tracking_number}")
    cainiao_info = get_cainiao_status(tracking_number)
    if cainiao_info:
        return cainiao_info

    # 2. Try configured WhereParcel API (if active in .env)
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

    # 3. Fallback: Simulated Mock Status
    status, detail = get_mock_status(tracking_number)
    return {
        "status": status,
        "details": f"[Simulated Status] {detail}",
        "provider": "mock"
    }

if __name__ == "__main__":
    # Test tracking status
    print("Testing direct Cainiao status:")
    print(get_tracking_status("LP00612345678901", "Cainiao"))
