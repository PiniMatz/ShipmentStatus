import os
import base64
import logging
from googleapiclient.discovery import build
from oauth_auth import get_gmail_creds
from email_parser import parse_email

logger = logging.getLogger(__name__)

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

    shipments = []
    try:
        service = build('gmail', 'v1', credentials=creds)
        # Search for both Amazon and AliExpress order/shipping emails on Gmail starting May 1st, 2026
        query = 'subject:("Amazon" OR "AliExpress") ("order" OR "shipment" OR "tracking" OR "shipped" OR "delivered" OR "confirmation") after:2026/05/01'
        
        # Get list of messages
        results = service.users().messages().list(userId='me', q=query, maxResults=50).execute()
        messages = results.get('messages', [])
        
        for msg in messages:
            msg_id = msg['id']
            detail = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            
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
