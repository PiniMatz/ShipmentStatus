import os
import sys
import json
import logging
import urllib.parse
from http.server import SimpleHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv

# Import our custom modules
from fetch_emails import fetch_all_shipments
from tracking import get_tracking_status
from database import load_shipments, save_shipments, upsert_shipments

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PORT = int(os.getenv("PORT", 8080))

def sync_and_update():
    """Fetches emails, upserts shipments, and updates live status of active packages."""
    logger.info("Executing Sync & Update...")
    
    # 1. Fetch from email inboxes
    new_shipments = fetch_all_shipments()
    
    # 2. Merge into local database
    db_shipments = upsert_shipments(new_shipments)
    
    # 3. Update status for shipments that are not delivered yet
    updated_any = False
    for shipment in db_shipments:
        status = shipment.get("status", "Unknown")
        tracking_num = shipment.get("tracking_number")
        carrier = shipment.get("carrier")
        
        # Don't poll if already delivered
        if status != "Delivered" and tracking_num:
            logger.info(f"Updating status for tracking: {tracking_num} ({carrier})")
            tracking_info = get_tracking_status(tracking_num, carrier)
            
            shipment["status"] = tracking_info.get("status", "Unknown")
            shipment["details"] = tracking_info.get("details", "")
            shipment["tracking_provider"] = tracking_info.get("provider", "")
            updated_any = True
            
    if updated_any:
        save_shipments(db_shipments)
        
    logger.info("Sync & Update completed successfully.")
    return db_shipments

def refresh_tracking_only():
    """Updates live status of active packages already in database, without fetching emails."""
    logger.info("Executing Refresh Tracking Only...")
    db_shipments = load_shipments()
    updated_any = False
    
    for shipment in db_shipments:
        status = shipment.get("status", "Unknown")
        tracking_num = shipment.get("tracking_number")
        carrier = shipment.get("carrier")
        
        # Don't poll if already delivered
        if status != "Delivered" and tracking_num:
            logger.info(f"Updating status for tracking: {tracking_num} ({carrier})")
            tracking_info = get_tracking_status(tracking_num, carrier)
            
            shipment["status"] = tracking_info.get("status", "Unknown")
            shipment["details"] = tracking_info.get("details", "")
            shipment["tracking_provider"] = tracking_info.get("provider", "")
            updated_any = True
            
    if updated_any:
        save_shipments(db_shipments)
        
    logger.info("Refresh Tracking Only completed successfully.")
    return db_shipments

class ShipmentStatusHandler(SimpleHTTPRequestHandler):
    
    def end_headers(self):
        # Allow CORS for easy development
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path == "/api/shipments":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = load_shipments()
            self.wfile.write(json.dumps(data).encode("utf-8"))
            
        elif parsed_path.path == "/api/sync":
            # Direct GET trigger for sync (optional convenience)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                updated_data = sync_and_update()
                self.wfile.write(json.dumps({"success": True, "shipments": updated_data}).encode("utf-8"))
            except Exception as e:
                logger.error(f"Sync error: {e}")
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                
        elif parsed_path.path == "/api/sync-statuses":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                updated_data = refresh_tracking_only()
                self.wfile.write(json.dumps({"success": True, "shipments": updated_data}).encode("utf-8"))
            except Exception as e:
                logger.error(f"Refresh error: {e}")
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                
        else:
            # Serve standard HTML/JS/CSS static files
            super().do_GET()

    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path == "/api/sync":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                updated_data = sync_and_update()
                self.wfile.write(json.dumps({"success": True, "shipments": updated_data}).encode("utf-8"))
            except Exception as e:
                logger.error(f"Sync error: {e}")
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                
        elif parsed_path.path == "/api/sync-statuses":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                updated_data = refresh_tracking_only()
                self.wfile.write(json.dumps({"success": True, "shipments": updated_data}).encode("utf-8"))
            except Exception as e:
                logger.error(f"Refresh error: {e}")
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                
        elif parsed_path.path == "/api/update":
            # Update metadata like phone number or notes
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                params = json.loads(post_data.decode("utf-8"))
                store = params.get("store")
                order_id = params.get("order_id")
                original_tracking = params.get("original_tracking_number")
                new_tracking = params.get("tracking_number")
                
                db_shipments = load_shipments()
                updated = False
                
                for s in db_shipments:
                    # Normalize None and empty values for tracking matching
                    s_tracking = s.get("tracking_number") or ""
                    orig_tracking_normalized = original_tracking or ""
                    
                    if s.get("store") == store and s.get("order_id") == order_id and s_tracking == orig_tracking_normalized:
                        if "phone" in params:
                            s["phone"] = params["phone"]
                        if "notes" in params:
                            s["notes"] = params["notes"]
                        if "carrier" in params:
                            s["carrier"] = params["carrier"]
                        
                        # Update tracking number
                        s["tracking_number"] = new_tracking if new_tracking else None
                        
                        # If tracking code was updated/added, fetch status immediately
                        if new_tracking and new_tracking != original_tracking:
                            logger.info(f"Manual tracking update. Fetching status for: {new_tracking}")
                            tracking_info = get_tracking_status(new_tracking, s.get("carrier"))
                            s["status"] = tracking_info.get("status", "Unknown")
                            s["details"] = tracking_info.get("details", "")
                            s["tracking_provider"] = tracking_info.get("provider", "")
                            
                        updated = True
                        break
                        
                if updated:
                    save_shipments(db_shipments)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
                else:
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": False, "error": "Shipment not found"}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                
        elif parsed_path.path == "/api/delete":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                params = json.loads(post_data.decode("utf-8"))
                store = params.get("store")
                order_id = params.get("order_id")
                tracking_number = params.get("tracking_number")
                
                db_shipments = load_shipments()
                filtered_shipments = []
                deleted = False
                
                for s in db_shipments:
                    s_tracking = s.get("tracking_number") or ""
                    tracking_normalized = tracking_number or ""
                    
                    if s.get("store") == store and s.get("order_id") == order_id and s_tracking == tracking_normalized:
                        deleted = True
                    else:
                        filtered_shipments.append(s)
                        
                if deleted:
                    save_shipments(filtered_shipments)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
                else:
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": False, "error": "Shipment not found"}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                
        else:
            self.send_response(404)
            self.end_headers()

def run_server():
    server_address = ("", PORT)
    httpd = HTTPServer(server_address, ShipmentStatusHandler)
    logger.info(f"Server running at http://localhost:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server shutting down.")
        httpd.server_close()

if __name__ == "__main__":
    if "--sync" in sys.argv:
        sync_and_update()
    else:
        run_server()
