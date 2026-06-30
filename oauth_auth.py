import os
import json
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


# --- OUTLOOK OAUTH ---
def get_outlook_token():
    try:
        import msal
    except ImportError:
        logger.error("MSAL library not installed yet.")
        return None

    client_id = os.getenv("OUTLOOK_CLIENT_ID")
    client_secret = os.getenv("OUTLOOK_CLIENT_SECRET") # Confidential app (if registered as Web/Confidential)
    # Note: Outlook supports PublicClientApplication (no secret) or ConfidentialClientApplication.
    # We will use PublicClientApplication since it supports acquire_token_interactive nicely on local.
    
    if not client_id:
        logger.warning("OUTLOOK_CLIENT_ID not found in .env. Skipping Outlook auth.")
        return None

    scopes = ["Mail.Read", "offline_access"]
    token_path = 'token_outlook.json'
    
    cache = msal.SerializableTokenCache()
    if os.path.exists(token_path):
        try:
            with open(token_path, 'r') as f:
                cache.deserialize(f.read())
        except Exception as e:
            logger.error(f"Error loading Outlook cache: {e}")

    # Build public client app
    app = msal.PublicClientApplication(
        client_id,
        authority="https://login.microsoftonline.com/common",
        token_cache=cache
    )

    # Try to get token from cache silently
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])

    if not result:
        # Fallback to interactive login
        # ponytail: msal handles browser redirect server automatically here
        try:
            result = app.acquire_token_interactive(scopes=scopes)
        except Exception as e:
            logger.error(f"Interactive Outlook auth failed: {e}")
            return None

        if "access_token" in result:
            if cache.has_state_changed:
                with open(token_path, 'w') as f:
                    f.write(cache.serialize())
        else:
            logger.error(f"Could not authenticate: {result.get('error_description')}")
            return None

    return result.get("access_token")

if __name__ == "__main__":
    print("Testing OAuth scripts...")
    # This can be run locally by the user to authenticate both inboxes.
    gmail_creds = get_gmail_creds()
    if gmail_creds:
        print("Gmail OAuth Authenticated successfully.")
    outlook_token = get_outlook_token()
    if outlook_token:
        print("Outlook OAuth Authenticated successfully.")
