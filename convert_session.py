"""
convert_session.py — À exécuter UNE SEULE FOIS en local.

Convertit le fichier userbot.session en SESSION_STRING (StringSession Telethon)
à coller comme variable d'environnement sur Railway.

Usage :
    python convert_session.py
"""

import os
import sys

from dotenv import load_dotenv
from telethon.sessions import StringSession
from telethon.sync import TelegramClient

load_dotenv()

API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")

if not API_ID or not API_HASH:
    sys.exit("Erreur : API_ID et API_HASH doivent être définis dans .env")

with TelegramClient("userbot", int(API_ID), API_HASH) as client:
    session_string = StringSession.save(client.session)

print("\n=== SESSION_STRING (copiez cette valeur dans Railway) ===\n")
print(session_string)
print("\n=========================================================\n")
