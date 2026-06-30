import os
import json
import logging

logger = logging.getLogger(__name__)
DB_PATH = "shipments.json"
DELETED_DB_PATH = "deleted_shipments.json"

def load_shipments():
    """Load shipments from local JSON database."""
    if not os.path.exists(DB_PATH):
        return []
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Deduplicate on load to automatically clean up database
            return deduplicate_database(data)
    except Exception as e:
        logger.error(f"Error loading shipments from database: {e}")
        return []

def save_shipments(shipments):
    """Save shipments to local JSON database."""
    try:
        # Deduplicate before saving
        clean_shipments = deduplicate_database(shipments)
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump(clean_shipments, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving shipments to database: {e}")
        return False

def load_deleted():
    """Load list of manually deleted shipments/orders."""
    if not os.path.exists(DELETED_DB_PATH):
        return []
    try:
        with open(DELETED_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading deleted list: {e}")
        return []

def save_deleted(deleted_list):
    """Save list of manually deleted shipments/orders."""
    try:
        with open(DELETED_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(deleted_list, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving deleted list: {e}")
        return False

def add_to_deleted(item):
    """Add a shipment's unique identifiers to the deleted database."""
    deleted = load_deleted()
    
    # Avoid duplicate deleted entries
    for d in deleted:
        if d.get("store") == item.get("store") and d.get("order_id") == item.get("order_id") and (d.get("tracking_number") or "") == (item.get("tracking_number") or ""):
            return
            
    deleted.append({
        "store": item.get("store"),
        "order_id": item.get("order_id"),
        "tracking_number": item.get("tracking_number")
    })
    save_deleted(deleted)

def deduplicate_database(shipments):
    """
    Remove duplicate shipments, keeping the latest/most complete information.
    Deduplicates based on order_id (if present) or tracking_number (if present).
    """
    by_order_id = {}
    by_tracking = {}
    standalone_items = [] # Items with neither order_id nor tracking_number
    
    for item in shipments:
        order_id = item.get("order_id")
        tracking_num = item.get("tracking_number")
        
        if not order_id and not tracking_num:
            standalone_items.append(item)
            continue
            
        matched_item = None
        if order_id and order_id in by_order_id:
            matched_item = by_order_id[order_id]
        elif tracking_num and tracking_num in by_tracking:
            matched_item = by_tracking[tracking_num]
            
        if matched_item:
            # Merge current item into matched_item
            for k, v in item.items():
                if v is not None and v != "":
                    existing_val = matched_item.get(k)
                    
                    if k in ["phone", "notes"]:
                        # Preserve manual fields if already populated
                        if not existing_val:
                            matched_item[k] = v
                    elif k == "status":
                        # Prefer actual carrier statuses over Simulated or Unknown
                        is_current_unknown = existing_val in ["Unknown", "Awaiting first sync", None]
                        is_new_real = v not in ["Unknown", "Awaiting first sync"]
                        if is_current_unknown or is_new_real:
                            matched_item[k] = v
                    elif k == "details":
                        is_current_unknown = existing_val in ["Awaiting first sync", "Awaiting status updates...", "", None]
                        is_new_real = v not in ["Awaiting first sync", "Awaiting status updates...", ""]
                        if is_current_unknown or is_new_real:
                            matched_item[k] = v
                    else:
                        matched_item[k] = v
            
            # Re-index under keys in case matched_item didn't have them originally
            if order_id:
                by_order_id[order_id] = matched_item
            if tracking_num:
                by_tracking[tracking_num] = matched_item
        else:
            # First time seeing this order / tracking number
            if order_id:
                by_order_id[order_id] = item
            if tracking_num:
                by_tracking[tracking_num] = item

    # Reconstruct unique list of shipments
    unique_items = []
    seen_ids = set()
    for item in list(by_order_id.values()) + list(by_tracking.values()) + standalone_items:
        item_id = id(item)
        if item_id not in seen_ids:
            seen_ids.add(item_id)
            unique_items.append(item)
            
    return unique_items

def upsert_shipments(new_shipments):
    """
    Merge new shipments into database.
    Excludes any shipments that have been explicitly deleted in the past.
    """
    existing = load_shipments()
    deleted = load_deleted()
    
    # Filter out new shipments that match any entry in the deleted list
    filtered_new = []
    for item in new_shipments:
        is_deleted = False
        item_tracking = item.get("tracking_number") or ""
        
        for d in deleted:
            d_tracking = d.get("tracking_number") or ""
            
            # Match by order_id
            if item.get("order_id") and item.get("order_id") == d.get("order_id"):
                is_deleted = True
                break
            # Match by tracking_number
            if item.get("tracking_number") and item_tracking == d_tracking:
                is_deleted = True
                break
                
        if not is_deleted:
            filtered_new.append(item)
            
    combined = existing + filtered_new
    updated_list = deduplicate_database(combined)
    
    # Initialize defaults for new shipments
    for item in updated_list:
        if "status" not in item:
            item["status"] = "Unknown"
        if "details" not in item:
            item["details"] = "Awaiting first sync"
            
    save_shipments(updated_list)
    return updated_list
