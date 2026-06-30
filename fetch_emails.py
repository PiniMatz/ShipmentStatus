import os
import base64
import logging
import requests
from googleapiclient.discovery import build
from oauth_auth import get_gmail_creds, get_outlook_token
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
        # Search only for AliExpress order/shipping emails on Gmail
        query = 'subject:("AliExpress") ("order" OR "shipment" OR "tracking" OR "shipped" OR "delivered" OR "confirmation")'
        
        # Get list of messages
        results = service.users().messages().list(userId='me', q=query, maxResults=30).execute()
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
            
            # Filter specifically for AliExpress
            if shipment['store'] == 'AliExpress' and (shipment['order_id'] or shipment['tracking_number']):
                shipment['email_id'] = msg_id
                shipment['source'] = 'Gmail'
                shipments.append(shipment)
                
    except Exception as e:
        logger.error(f"Error fetching Gmail messages: {e}")

    return shipments


# --- OUTLOOK FETCH ---
def fetch_outlook_shipments():
    token = get_outlook_token()
    if not token:
        logger.info("Outlook credentials not available. Skipping Outlook fetch.")
        return []

    shipments = []
    try:
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        # Search only for Amazon order/shipping emails on Outlook
        search_query = '"Amazon" AND ("order" OR "shipment" OR "tracking" OR "shipped" OR "delivered" OR "confirmation")'
        url = f"https://graph.microsoft.com/v1.0/me/messages?$search={search_query}&$top=30"
        
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            logger.error(f"Outlook Graph API returned error {response.status_code}: {response.text}")
            return []
            
        data = response.json()
        messages = data.get('value', [])
        
        for msg in messages:
            msg_id = msg.get('id')
            subject = msg.get('subject', '')
            sender = msg.get('from', {}).get('emailAddress', {}).get('address', '')
            body = msg.get('body', {}).get('content', '')
            
            shipment = parse_email(subject, body, sender)
            
            # Filter specifically for Amazon
            if "Amazon" in shipment['store'] and (shipment['order_id'] or shipment['tracking_number']):
                shipment['email_id'] = msg_id
                shipment['source'] = 'Outlook'
                shipments.append(shipment)
                
    except Exception as e:
        logger.error(f"Error fetching Outlook messages: {e}")

    return shipments

def fetch_all_shipments():
    """Fetch shipments from both Gmail and Outlook inboxes."""
    logger.info("Starting email fetch...")
    gmail_shipments = fetch_gmail_shipments()
    outlook_shipments = fetch_outlook_shipments()
    
    # Merge and remove duplicates (by order_id and tracking_number)
    seen = set()
    all_shipments = []
    
    for s in gmail_shipments + outlook_shipments:
        # Create a unique key
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
