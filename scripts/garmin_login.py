"""One-time Garmin login. Run on your own computer:

    pip install garminconnect
    python garmin_login.py

It asks for your Garmin email, password and (if on) your MFA code, then
prints a token blob. Paste that blob into GitHub:
repo Settings > Secrets and variables > Actions > New repository secret,
name GARMIN_TOKENS. Your password is never saved anywhere.
"""
from getpass import getpass

from garminconnect import Garmin

email = input("Garmin email: ").strip()
password = getpass("Garmin password (hidden): ")
api = Garmin(email, password, prompt_mfa=lambda: input("MFA code from Garmin: ").strip())
api.login()
print("\nLogged in as", api.get_full_name())
print("\n===== COPY EVERYTHING BETWEEN THE LINES INTO THE GARMIN_TOKENS SECRET =====")
print(api.client.dumps())
print("===== END =====")
