"""Generate a local Gmail OAuth refresh token for Render configuration.

Run manually on a trusted developer machine. This utility is never imported by
the FastAPI application and performs no authorization during app startup.
"""

import argparse
import json
import os
from pathlib import Path

SCOPE = "https://www.googleapis.com/auth/gmail.send"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CLIENT_FILE = PROJECT_ROOT / "credentials.json"
OUTPUT_FILE = PROJECT_ROOT / ".gmail_token.json"


def generate_token(client_file: Path = DEFAULT_CLIENT_FILE) -> Path:
    """Run local OAuth consent and store only required credentials in an ignored file."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not client_file.is_file():
        raise FileNotFoundError("Desktop OAuth client JSON file was not found.")
    if OUTPUT_FILE.exists():
        raise FileExistsError(".gmail_token.json already exists; move or securely remove it before generating a replacement.")

    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), scopes=[SCOPE])
    # Offline access returns a refresh token; explicit consent helps obtain a
    # new refresh token if this Google account previously authorized the client.
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not credentials.refresh_token:
        raise RuntimeError("Google did not return a refresh token. Revoke the existing grant and run this utility again.")

    payload = {
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "scopes": [SCOPE],
    }
    file_descriptor = os.open(OUTPUT_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(file_descriptor, "w", encoding="utf-8") as output:
        json.dump(payload, output, indent=2)
        output.write("\n")
    return OUTPUT_FILE


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Gmail API refresh credentials for local Render configuration.")
    parser.add_argument(
        "--client-secrets",
        type=Path,
        default=DEFAULT_CLIENT_FILE,
        help="Downloaded Desktop OAuth client JSON (default: ./credentials.json)",
    )
    args = parser.parse_args()
    try:
        output = generate_token(args.client_secrets)
    except Exception as exc:
        # Do not print exception details from OAuth libraries; they may contain
        # authorization URLs or sensitive request data.
        raise SystemExit(f"Gmail OAuth token generation failed ({type(exc).__name__}); details suppressed.") from None
    print(f"Credentials saved to {output}. Keep this file private and do not commit it.")


if __name__ == "__main__":
    main()
