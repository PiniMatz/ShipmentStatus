import re
import html
import base64
import logging
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

# A simple HTML to text converter using standard library HTMLParser
class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = []

    def handle_data(self, d):
        self.text.append(d)

    def get_data(self):
        return ''.join(self.text)

def strip_tags(html_content):
    s = HTMLStripper()
    try:
        s.feed(html_content)
        return html.unescape(s.get_data())
    except Exception as e:
        logger.warning(f"Error stripping HTML: {e}")
        # Fallback: simple regex tag strip
        clean = re.sub(r'<[^>]+>', ' ', html_content)
        return html.unescape(clean)

# Common regex patterns for tracking numbers
TRACKING_PATTERNS = {
    "UPS": r"\b1Z[A-Z0-9]{16}\b",
    "USPS": r"\b(9[1-5]\d{20}|82\d{8}|70\d{18}|14\d{18}|23\d{18}|03\d{18})\b",
    "FedEx": r"\b(96\d{20}|\d{15}|\d{12})\b",
    "DHL": r"\b(\d{10})\b",
    # AliExpress/China Post: LP + 14 digits, or 2 letters + 9 digits + 2 letters (e.g. LL123456789CN)
    "Cainiao": r"\bLP\d{14}\b",
    "China Post": r"\b[A-Z]{2}\d{9}[A-Z]{2}\b",
}

def parse_email(subject, body, sender):
    """
    Parses a single email subject and body to detect store, order ID, and tracking details.
    """
    subject_lower = subject.lower()
    sender_lower = sender.lower()
    
    # Strip HTML if needed to get clean text
    is_html = "<html" in body.lower() or "<div" in body.lower()
    text_content = strip_tags(body) if is_html else body
    text_content_lower = text_content.lower()
    
    # 1. Detect store
    store = "Unknown Store"
    if "amazon" in sender_lower or "amazon" in subject_lower:
        # Detect Amazon region
        if ".co.uk" in sender_lower or ".co.uk" in subject_lower:
            store = "Amazon UK"
        elif ".de" in sender_lower or ".de" in subject_lower:
            store = "Amazon DE"
        else:
            store = "Amazon US"
    elif "amazon" in text_content_lower:
        if "amazon.co.uk" in text_content_lower:
            store = "Amazon UK"
        elif "amazon.de" in text_content_lower:
            store = "Amazon DE"
        else:
            store = "Amazon US"
    elif "aliexpress" in sender_lower or "aliexpress" in subject_lower or "aliexpress" in text_content_lower:
        store = "AliExpress"
    
    # 2. Extract Order ID
    order_id = None
    if "amazon" in store.lower():
        # Amazon pattern: 123-1234567-1234567
        order_match = re.search(r"\b\d{3}-\d{7}-\d{7}\b", text_content)
        if not order_match:
            order_match = re.search(r"\b\d{3}-\d{7}-\d{7}\b", subject)
        if order_match:
            order_id = order_match.group(0)
    elif store == "AliExpress":
        # AliExpress pattern: 15 to 18 digits
        order_match = re.search(r"\b(order|id|no\.?)\s*:?\s*(\d{15,18})\b", text_content, re.IGNORECASE)
        if not order_match:
            order_match = re.search(r"\b\d{15,18}\b", subject)
        if not order_match:
            # Try to search any 15-18 digits in body
            order_match = re.search(r"\b\d{15,18}\b", text_content)
        if order_match:
            order_id = order_match.group(2) if len(order_match.groups()) >= 2 else order_match.group(0)

    # 3. Extract Tracking Number and Carrier
    tracking_number = None
    carrier = "Unknown Carrier"
    
    # First, look for tracking patterns in the raw HTML links (often contains deep links with tracking nums)
    if is_html:
        # Extract href attributes
        links = re.findall(r'href=["\'](https?://[^"\']+)["\']', body)
        for link in links:
            # Check Cainiao/AliExpress tracking link
            # e.g., https://global.cainiao.com/newDetail.htm?mailNoList=LP00612345678901
            cainiao_match = re.search(r"(mailNoList|trackNums|nums|trackingId)=([A-Z0-9]+)", link, re.IGNORECASE)
            if cainiao_match:
                tracking_number = cainiao_match.group(2)
                carrier = "Cainiao"
                break
            
            # Check Amazon tracking link
            # e.g. amazon.com/progress-tracker?orderId=...
            if "progress-tracker" in link:
                # Amazon handles its own shipping or uses carrier, often tracking is inside the page
                carrier = "Amazon Shipping"
                
    # If no tracking number from links, check regexes on clean text
    if not tracking_number:
        # Look for "tracking number", "tracking", "track #", etc.
        # e.g. "tracking number: LL123456789CN"
        context_match = re.search(r"(tracking\s*(number|#)?|track\s*#?)\s*:?\s*([A-Z0-9]+)", text_content, re.IGNORECASE)
        if context_match:
            candidate = context_match.group(3).strip()
            # Validate if candidate matches any carrier format
            for name, pattern in TRACKING_PATTERNS.items():
                if re.match(pattern, candidate):
                    tracking_number = candidate
                    carrier = name
                    break
                    
    # If still not found, scan the entire text for any carrier pattern
    if not tracking_number:
        for name, pattern in TRACKING_PATTERNS.items():
            match = re.search(pattern, text_content)
            if match:
                tracking_number = match.group(0)
                carrier = name
                break
                
    # If we have an AliExpress order but carrier is unknown, and we found a numeric tracking number
    if store == "AliExpress" and not tracking_number:
        # Sometimes tracking number is just same 15-18 digit number or Cainiao numbers
        # Cainiao numbers can be 15-18 digits or LP...
        cainiao_match = re.search(r"\b(LP\d{14}|\d{15,18})\b", text_content)
        if cainiao_match:
            tracking_number = cainiao_match.group(0)
            carrier = "Cainiao"

    return {
        "store": store,
        "order_id": order_id,
        "tracking_number": tracking_number,
        "carrier": carrier,
        "subject": subject,
        "sender": sender
    }
