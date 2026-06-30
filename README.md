# TrackFlow: Unified Inbox Shipment Monitor

A lightweight, zero-dependency local dashboard to automatically track your packages from Gmail & Outlook inboxes, fetch their live shipping statuses, and manage recipient phone numbers and custom notes.

## Features
- **OAuth 2.0 Secure Auth**: No passwords stored locally. Token refresh is handled automatically.
- **Inbox Scanner**: Scans Gmail & Outlook for Amazon and AliExpress emails.
- **Smart Parsing**: Extracts Order IDs, Carriers (UPS, USPS, FedEx, DHL, Cainiao), and Tracking Numbers.
- **Dashboard**: Sleek glassmorphism dark theme UI to filter, search, copy codes, and edit shipment notes/phone numbers.
- **Pluggable Carrier Status**: Supports live programmatic status tracking via mock fallback or free-tier APIs (WhereParcel/ShipEngine).
- **Scheduled Syncing**: Command-line interface support for automated twice-daily syncing.

## Setup Instructions

1. **Clone & Install Dependencies**:
   ```bash
   pip install google-auth-oauthlib google-api-python-client msal requests python-dotenv
   ```

2. **Configure environment variable credentials**:
   - Copy `.env.example` to `.env`.
   - Put your Google Cloud Console Client credentials (`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`) and Azure AD client ID (`OUTLOOK_CLIENT_ID`) in `.env`.

3. **Run the local server**:
   ```bash
   python backend.py
   ```
   - Open your browser at `http://localhost:8080`.
   - On the first load, clicking **Sync Inboxes** will open Google and Microsoft authentication pages in your browser to authorize access to your mails securely. Refresh tokens will be cached locally in `token_gmail.json` and `token_outlook.json`.

4. **Automated scheduled scans**:
   To sync your packages twice daily in the background, set up a cron job or Windows Task Scheduler to execute:
   ```bash
   python backend.py --sync
   ```

## Development and Verification
Run the parser tests:
```bash
python test_parser.py
```
