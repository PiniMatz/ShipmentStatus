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

def get_tracking_status(tracking_number, carrier_name):
    """
    Fetch tracking status from the configured provider.
    Falls back to Mock if keys are missing.
    """
    provider = os.getenv("TRACKING_PROVIDER", "mock").lower()
    
    if provider == "mock" or not tracking_number:
        status, detail = get_mock_status(tracking_number)
        return {
            "status": status,
            "details": detail,
            "provider": "mock"
        }
        
    if provider == "whereparcel":
        api_key = os.getenv("WHEREPARCEL_API_KEY")
        secret_key = os.getenv("WHEREPARCEL_SECRET_KEY")
        
        if not api_key or not secret_key:
            logger.warning("WhereParcel keys missing from .env. Falling back to Mock.")
            status, detail = get_mock_status(tracking_number)
            return {
                "status": status,
                "details": detail,
                "provider": "mock (fallback)"
            }
            
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
                # Assuming standard response fields based on common API schemas:
                # e.g., data['status'] or data['tracking']['status']
                tracking_info = data.get("tracking", data)
                status = tracking_info.get("status", "In Transit")
                detail = tracking_info.get("lastEvent", {}).get("description", "In transit to destination")
                
                return {
                    "status": status,
                    "details": detail,
                    "provider": "whereparcel"
                }
            else:
                logger.error(f"WhereParcel API returned code {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"WhereParcel API connection error: {e}")
            
        # Fallback to mock on API failure
        status, detail = get_mock_status(tracking_number)
        return {
            "status": status,
            "details": f"API Error. Fallback status: {detail}",
            "provider": "mock (fallback)"
        }
        
    # Default fallback
    status, detail = get_mock_status(tracking_number)
    return {
        "status": status,
        "details": detail,
        "provider": "mock"
    }

if __name__ == "__main__":
    # Test tracking status
    print("Testing Mock tracking status:")
    print(get_tracking_status("1Z999AA10123456784", "UPS"))
    print(get_tracking_status("9400111899223456789012", "USPS"))
