import os
import json
import base64
import logging
from googleapiclient.discovery import build
from oauth_auth import get_gmail_creds
from email_parser import parse_email

logger = logging.getLogger(__name__)
LAST_SCAN_PATH = "last_scan.json"
DEFAULT_START_TS = 1777593600 # May 1st, 2026 00:00:00 UTC

def load_last_scan_timestamp():
    """Load the timestamp of the latest email parsed in the last scan."""
    if not os.path.exists(LAST_SCAN_PATH):
        return DEFAULT_START_TS
    try:
        with open(LAST_SCAN_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("last_scan_timestamp", DEFAULT_START_TS)
    except Exception as e:
        logger.error(f"Error loading last scan timestamp: {e}")
        return DEFAULT_START_TS

def save_last_scan_timestamp(ts):
    """Save the timestamp of the latest email parsed in this scan."""
    try:
        with open(LAST_SCAN_PATH, "w", encoding="utf-8") as f:
            json.dump({"last_scan_timestamp": ts}, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving last scan timestamp: {e}")
        return False

# --- GMAIL FETCH ---
def get_gmail_body_text(payload):
    """Recursively parse parts of Gmail message payload to get the body text."""
    if 'parts' in payload:
        text = ""
        for part in payload['parts']:
            text += get_gmail_body_text(part)
        return text
    
    body = payload.get('body', {})
    data = body.get('data')
    if data:
        try:
            # Gmail uses base64url encoding
            decoded = base64.urlsafe_b64decode(data.encode('ASCII')).decode('utf-8', errors='ignore')
            return decoded
        except Exception as e:
            logger.warning(f"Error decoding Gmail body part: {e}")
    return ""

def fetch_gmail_shipments():
    creds = get_gmail_creds()
    if not creds:
        logger.info("Gmail credentials not available. Skipping Gmail fetch.")
        return []

    last_ts = load_last_scan_timestamp()
    # Backtrack 5 minutes (300 seconds) to avoid missing emails due to delivery delays/sync timings
    query_ts = max(DEFAULT_START_TS, last_ts - 300)
    
    shipments = []
    max_msg_ts = last_ts
    
    try:
        service = build('gmail', 'v1', credentials=creds)
        # Query messages received AFTER our last scan timestamp
        query = f'("Amazon" OR "AliExpress" OR "Ordered") ("order" OR "shipment" OR "tracking" OR "shipped" OR "delivered" OR "confirmation") after:{query_ts}'
        logger.info(f"Querying Gmail for new messages since epoch: {query_ts} (Query: {query})")
        
        # Get list of messages
        results = service.users().messages().list(userId='me', q=query, maxResults=50).execute()
        messages = results.get('messages', [])
        logger.info(f"Gmail returned {len(messages)} matching messages for delta scan.")
        
        for msg in messages:
            msg_id = msg['id']
            detail = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            
            # Record internal date (convert ms to seconds)
            internal_date_sec = int(detail.get('internalDate', 0)) // 1000
            if internal_date_sec > max_msg_ts:
                max_msg_ts = internal_date_sec
                
            headers = detail.get('payload', {}).get('headers', [])
            subject = ""
            sender = ""
            for h in headers:
                if h['name'].lower() == 'subject':
                    subject = h['value']
                elif h['name'].lower() == 'from':
                    sender = h['value']
            
            body = get_gmail_body_text(detail.get('payload', {}))
            shipment = parse_email(subject, body, sender)
            
            # Keep if we extracted an Order ID or a Tracking Number
            if shipment['order_id'] or shipment['tracking_number']:
                shipment['email_id'] = msg_id
                shipment['source'] = 'Gmail'
                shipments.append(shipment)
                
        # Save the new highest email timestamp processed
        if messages:
            save_last_scan_timestamp(max_msg_ts)
            logger.info(f"Delta scan timestamp updated to: {max_msg_ts}")
                
    except Exception as e:
        logger.error(f"Error fetching Gmail messages: {e}")

    return shipments

def fetch_all_shipments():
    """Fetch shipments from authorized Gmail inbox (supporting both forwarded Amazon and AliExpress)."""
    logger.info("Starting email fetch...")
    gmail_shipments = fetch_gmail_shipments()
    
    # Remove duplicates (by store, order_id and tracking_number)
    seen = set()
    all_shipments = []
    
    for s in gmail_shipments:
        key = (s['store'], s['order_id'], s['tracking_number'])
        if key not in seen:
            seen.add(key)
            all_shipments.append(s)
            
    logger.info(f"Fetch completed. Found {len(all_shipments)} shipments.")
    return all_shipments

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Test fetch
    results = fetch_all_shipments()
    print(f"Results: {results}")
