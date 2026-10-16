import os, re, asyncio, threading
from urllib.parse import quote
from flask import Flask, request, jsonify, Response
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
SESSION = os.environ.get("TG_SESSION")  # make_session.py থেকে পাওয়া লেখা (হোস্টিং সার্ভারের জন্য)
PORT = int(os.environ.get("PORT", 8000))
BLOCKED_EXT = {".apk"}  # দরকার না হলে ফাঁকা সেট করুন: set()
CHUNK = 512 * 1024
HERE = os.path.dirname(os.path.abspath(__file__))

# Telethon একটি আলাদা থ্রেডের event loop-এ চলে, Flask সাধারণ থ্রেডে
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()


def run(coro):
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


async def _init():
    sess = StringSession(SESSION) if SESSION else os.path.join(HERE, "session")
    c = TelegramClient(sess, API_ID, API_HASH)
    if BOT_TOKEN:
        await c.start(bot_token=BOT_TOKEN)
    else:
        await c.start()
    return c


client = run(_init())
app = Flask(__name__)

LINK = re.compile(
    r"^(?:https?://)?(?:t\.me|telegram\.me)/(?:s/)?([A-Za-z][A-Za-z0-9_]{3,31})/(\d+)(?:[/?#].*)?$"
)
PRIVATE = re.compile(r"(t\.me|telegram\.me)/(c/|\+|joinchat)")


class Bad(Exception):
    def __init__(self, msg, code=400):
        self.msg, self.code = msg, code


@app.errorhandler(Bad)
def on_bad(e):
    return jsonify(error=e.msg), e.code


@app.errorhandler(Exception)
def on_err(e):
    return jsonify(error="সার্ভারে সমস্যা হয়েছে: " + str(e)[:120]), 502


@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = os.environ.get("ALLOW_ORIGIN", "*")
    resp.headers["Access-Control-Expose-Headers"] = "Content-Disposition, Content-Length"
    return resp


def get_msg(url):
    url = (url or "").strip()
    if PRIVATE.search(url):
        raise Bad("এটা প্রাইভেট গ্রুপ/চ্যানেলের লিংক। শুধু পাবলিক চ্যানেলের লিংক চলবে।")
    m = LINK.match(url)
    if not m:
        raise Bad("লিংকটা সঠিক নয়। উদাহরণ: https://t.me/channel_name/123")
    channel, mid = m.group(1), int(m.group(2))
    msg = run(client.get_messages(channel, ids=mid))
    if not msg:
        raise Bad("মেসেজটা পাওয়া যায়নি। মুছে ফেলা হতে পারে, অথবা চ্যানেল পাবলিক নয়।", 404)
    if not msg.file:
        raise Bad("এই মেসেজে কোনো ফাইল বা ভিডিও নেই।", 404)
    name = msg.file.name or "telegram_%s_%s%s" % (channel, mid, msg.file.ext or "")
    ext = os.path.splitext(name)[1].lower()
    if ext in BLOCKED_EXT:
        raise Bad("নিরাপত্তার কারণে এই ধরনের ফাইল ডাউনলোড বন্ধ।", 403)
    return msg, name


@app.get("/")
def home():
    return "ok"


@app.get("/api/info")
def info():
    msg, name = get_msg(request.args.get("url"))
    return jsonify(name=name, size=msg.file.size or 0, mime=msg.file.mime_type or "")


@app.get("/api/download")
def download():
    msg, name = get_msg(request.args.get("url"))

    async def chunks():
        async for c in client.iter_download(msg.media, request_size=CHUNK):
            yield c

    def stream():
        agen = chunks()
        try:
            while True:
                try:
                    yield run(agen.__anext__())
                except StopAsyncIteration:
                    break
        finally:
            run(agen.aclose())

    ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", name) or "file"
    headers = {
        "Content-Disposition": "attachment; filename=\"%s\"; filename*=UTF-8''%s"
        % (ascii_name, quote(name)),
    }
    if msg.file.size:
        headers["Content-Length"] = str(msg.file.size)
    return Response(stream(), mimetype=msg.file.mime_type or "application/octet-stream", headers=headers)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
