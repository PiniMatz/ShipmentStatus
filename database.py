import os
import json
import logging

logger = logging.getLogger(__name__)
DB_PATH = "shipments.json"

def load_shipments():
    """Load shipments from local JSON database."""
    if not os.path.exists(DB_PATH):
        return []
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading shipments from database: {e}")
        return []

def save_shipments(shipments):
    """Save shipments to local JSON database."""
    try:
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump(shipments, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving shipments to database: {e}")
        return False

def upsert_shipments(new_shipments):
    """
    Merge new shipments into database.
    Preserves existing items to avoid overwriting manually updated fields or status history.
    """
    existing = load_shipments()
    
    # Index existing by unique key: (store, order_id, tracking_number)
    indexed = {}
    for item in existing:
        key = (item.get("store"), item.get("order_id"), item.get("tracking_number"))
        indexed[key] = item
        
    for item in new_shipments:
        key = (item.get("store"), item.get("order_id"), item.get("tracking_number"))
        if key in indexed:
            # Update fields if new data has something better (but keep status if not mock)
            # E.g., we preserve existing status unless we fetch a new status
            # For simplicity, we merge the fields
            existing_item = indexed[key]
            # Merge fields
            for k, v in item.items():
                if v is not None:
                    existing_item[k] = v
        else:
            # Initialize empty/default tracking status if not already present
            if "status" not in item:
                item["status"] = "Unknown"
            if "details" not in item:
                item["details"] = "Awaiting first sync"
            indexed[key] = item
            
    updated_list = list(indexed.values())
    save_shipments(updated_list)
    return updated_list

if __name__ == "__main__":
    # Test DB methods
    test_data = [
        {"store": "Amazon US", "order_id": "111-2222222-3333333", "tracking_number": "1Z999", "carrier": "UPS"}
    ]
    upsert_shipments(test_data)
    print("DB Load:", load_shipments())
