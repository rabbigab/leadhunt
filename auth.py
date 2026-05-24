"""
auth.py — À exécuter UNE SEULE FOIS en local pour générer le fichier de session Telethon.

Usage :
    python auth.py

Le fichier `userbot.session` sera créé dans le répertoire courant.
Convertissez-le ensuite en SESSION_STRING avec convert_session.py.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

load_dotenv()

API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")

if not API_ID or not API_HASH:
    sys.exit("Erreur : API_ID et API_HASH doivent être définis dans .env")


async def main() -> None:
    client = TelegramClient("userbot", int(API_ID), API_HASH)
    await client.start()

    if not await client.is_user_authorized():
        phone = input("Numéro de téléphone (format international, ex: +33612345678) : ").strip()
        await client.send_code_request(phone)
        code = input("Code reçu par SMS/Telegram : ").strip()
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            password = input("Mot de passe 2FA : ").strip()
            await client.sign_in(password=password)

    me = await client.get_me()
    print(f"\nConnecté en tant que : {me.first_name} (@{me.username})")
    print("Fichier de session 'userbot.session' créé avec succès.")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
