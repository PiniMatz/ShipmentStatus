import os
import logging
from dotenv import load_dotenv

# Load env variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- GMAIL OAUTH ---
def get_gmail_creds():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        logger.error("Google auth libraries not installed yet.")
        return None

    scopes = ['https://www.googleapis.com/auth/gmail.readonly']
    creds = None
    token_path = 'token_gmail.json'

    # Check if we already have saved credentials
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, scopes)
        except Exception as e:
            logger.error(f"Error loading Gmail token: {e}")

    # If credentials don't exist or are invalid, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.error(f"Error refreshing Gmail token: {e}")
                creds = None
        
        if not creds:
            # Try to discover any client secret JSON file in the directory first
            secret_file = None
            for filename in os.listdir('.'):
                if (filename.startswith('client_secret_') or filename == 'credentials_gmail.json') and filename.endswith('.json'):
                    secret_file = filename
                    break

            if secret_file:
                logger.info(f"Loading Gmail OAuth client config from file: {secret_file}")
                flow = InstalledAppFlow.from_client_secrets_file(secret_file, scopes)
            else:
                client_id = os.getenv("GMAIL_CLIENT_ID")
                client_secret = os.getenv("GMAIL_CLIENT_SECRET")
                if not client_id or not client_secret:
                    logger.warning("Gmail client credentials not found (no client_secret_*.json file or GMAIL_CLIENT_ID in .env). Skipping Gmail auth.")
                    return None

                client_config = {
                    "installed": {
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": ["http://localhost"]
                    }
                }
                flow = InstalledAppFlow.from_client_config(client_config, scopes)
            
            # Open browser for local authentication
            creds = flow.run_local_server(port=0, prompt='consent')
            
        # Save credentials for future runs
        with open(token_path, 'w') as token_file:
            token_file.write(creds.to_json())

    return creds

if __name__ == "__main__":
    print("Testing OAuth scripts...")
    gmail_creds = get_gmail_creds()
    if gmail_creds:
        print("Gmail OAuth Authenticated successfully.")
