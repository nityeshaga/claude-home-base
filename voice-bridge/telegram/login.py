"""One-time sign-in for the Telegram front door. Creates <TG_SESSION>.session in this directory.

Needs TG_API_ID and TG_API_HASH (create an app at https://my.telegram.org) and TG_PHONE
(the number of the account the assistant will answer as; use a dedicated number, not your own).
Run from this directory with the telegram venv:  TG_PHONE=+1... venv/bin/python login.py
"""
import asyncio, os
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded


async def main():
    phone = os.environ["TG_PHONE"]
    app = Client(os.environ.get("TG_SESSION", "voice"), api_id=int(os.environ["TG_API_ID"]),
                 api_hash=os.environ["TG_API_HASH"], phone_number=phone, workdir=".")
    await app.connect()
    sent = await app.send_code(phone)
    print("code sent via", sent.type)
    code = input("login code: ").strip()
    try:
        user = await app.sign_in(phone, sent.phone_code_hash, code)
    except SessionPasswordNeeded:
        user = await app.check_password(input("2FA password: ").strip())
    print("signed in as", user.id, user.first_name, user.username)
    await app.disconnect()


asyncio.run(main())
