# একবার নিজের ফোনে চালান। ফোন নম্বর ও কোড দিলে একটি লম্বা লেখা (TG_SESSION) ছাপবে।
# সতর্কতা: এই লেখা দিয়ে অ্যাকাউন্টে ঢোকা যায়। কাউকে দেবেন না, GitHub-এ রাখবেন না।
import os
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
with TelegramClient(StringSession(), int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"]) as c:
    print("\nTG_SESSION=" + c.session.save())
