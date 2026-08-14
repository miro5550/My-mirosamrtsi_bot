import os
import asyncio
from collections import defaultdict, deque

import aiohttp
from openai import AsyncOpenAI


# =========================================================
# CONFIG
# =========================================================

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

# You can change this model if your OpenAI project uses another model.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

client = AsyncOpenAI(api_key=OPENAI_API_KEY)


# =========================================================
# BOT PERSONALITY
# =========================================================

SYSTEM_PROMPT = """
تۆ Miro AI ـیت، یارمەتیدەرێکی زیرەک و سروشتی.

زمان:
- کوردیی سۆرانی بە باشی تێبگە.
- کوردیی لاتینی بە باشی تێبگە.
- ئەگەر بەکارهێنەر بە لاتینی کوردی نووسی، دەتوانیت بە لاتینی کوردی وەڵام بدەیت.
- ئەگەر بە سۆرانی نووسی، بە سۆرانی وەڵام بدە.
- ئەگەر زمانێکی تر بەکار هێنا، بە هەمان زمان وەڵام بدە.

شێوازی قسەکردن:
- وەک مرۆڤێکی ئاسایی و سروشتی قسە بکە.
- وەڵامەکانت زۆر ڕۆبۆتی و فەرمی مەکە.
- کورت و ڕوون وەڵام بدە، مەگەر بەکارهێنەر داوای وردەکاری بکات.
- کاتێک گونجاوە emoji بەکاربهێنە، بەڵام زۆر مەکە.
- ئەگەر بەکارهێنەر گاڵتە دەکات، بە شێوەیەکی سروشتی وەڵام بدە.
- ئەگەر پرسیارەکە جددییە، جددی و یارمەتیدەر بە.
- هیچکات مەڵێ "من AI ـم" بەبێ ئەوەی بەکارهێنەر بە ڕوونی پرسیار بکات.

Memory:
- گفتوگۆی کورت لەگەڵ هەر بەکارهێنەرێک لە context ـەکەدا بەکاربهێنە.
- ئەو زانیارییەی لە گفتوگۆی ئێستادا پێویستە لەبەر بگرە.
- هیچ زانیارییەکی نهێنی یان هەستیار داوا مەکە.

گرنگ:
- هەرگیز Telegram Token یان API Key داوا مەکە.
- ئەگەر نەتوانیت شتێک بکەیت، بە ڕوونی بڵێ.
"""


# =========================================================
# SHORT MEMORY
# =========================================================

# Keeps the latest 12 messages for every chat.
memory = defaultdict(lambda: deque(maxlen=12))


# =========================================================
# OPENAI
# =========================================================

async def ask_ai(chat_id: int, user_message: str) -> str:

    history = list(memory[chat_id])

    # Add current message to memory
    memory[chat_id].append({
        "role": "user",
        "content": user_message
    })

    # Build a simple conversation context
    conversation = []

    for item in history:
        conversation.append(
            f"{item['role']}: {item['content']}"
        )

    conversation.append(
        f"user: {user_message}"
    )

    prompt = "\n".join(conversation)

    try:
        response = await client.responses.create(
            model=OPENAI_MODEL,
            instructions=SYSTEM_PROMPT,
            input=prompt
        )

        answer = response.output_text.strip()

        if not answer:
            answer = "ببورە 🤍 ئێستا نەمتوانی وەڵامێکی گونجاو دروست بکەم."

        # Save AI answer
        memory[chat_id].append({
            "role": "assistant",
            "content": answer
        })

        return answer

    except Exception as e:
        print("AI ERROR:", repr(e))

        return (
            "ببورە 🤍 ئێستا کێشەیەک لە بەشی AI ڕوویدا. "
            "تکایە دووبارە هەوڵ بدەرەوە."
        )


# =========================================================
# TELEGRAM
# =========================================================

async def telegram_request(
    session,
    method: str,
    data: dict | None = None
):

    url = f"{TELEGRAM_API}/{method}"

    async with session.post(
        url,
        json=data or {},
        timeout=aiohttp.ClientTimeout(total=60)
    ) as response:

        return await response.json()


async def send_message(
    session,
    chat_id: int,
    text: str
):

    # Telegram text limit is 4096 characters.
    chunks = [
        text[i:i + 4000]
        for i in range(0, len(text), 4000)
    ]

    for chunk in chunks:
        await telegram_request(
            session,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": chunk
            }
        )


# =========================================================
# COMMANDS
# =========================================================

async def handle_command(
    session,
    chat_id: int,
    text: str
):

    command = text.split()[0].lower()

    if command == "/start":
        memory[chat_id].clear()

        await send_message(
            session,
            chat_id,
            "سڵاو 🤍 من Miro AI ـم.\n"
            "هەر شتێکت دەوێت بنووسە، قسە دەکەین 😊"
        )

        return True

    if command == "/help":
        await send_message(
            session,
            chat_id,
            "🤍 دەتوانیت ڕاستەوخۆ پەیامم بۆ بنێریت.\n\n"
            "کوردی سۆرانی، کوردی لاتینی و چەند زمانێکی تر تێدەگەم."
        )

        return True

    if command == "/about":
        await send_message(
            session,
            chat_id,
            "Miro AI 🤍\n"
            "یارمەتیدەرێکی AI ـە بۆ گفتوگۆ و وەڵامدانەوە."
        )

        return True

    return False


# =========================================================
# UPDATE HANDLER
# =========================================================

async def process_update(
    session,
    update
):

    message = update.get("message")

    if not message:
        return

    # Ignore messages without text
    text = message.get("text")

    if not text:
        return

    chat = message.get("chat")

    if not chat:
        return

    chat_id = chat["id"]

    # Commands
    if text.startswith("/"):
        handled = await handle_command(
            session,
            chat_id,
            text
        )

        if handled:
            return

    # Show typing status
    await telegram_request(
        session,
        "sendChatAction",
        {
            "chat_id": chat_id,
            "action": "typing"
        }
    )

    # Ask AI
    answer = await ask_ai(
        chat_id,
        text
    )

    # Send answer
    await send_message(
        session,
        chat_id,
        answer
    )


# =========================================================
# MAIN LOOP
# =========================================================

async def main():

    offset = None

    print("Miro AI Telegram Bot is starting...")

    async with aiohttp.ClientSession() as session:

        # Check bot
        me = await telegram_request(
            session,
            "getMe"
        )

        if not me.get("ok"):
            print("Telegram error:", me)
            return

        print(
            "Connected to Telegram as:",
            me["result"].get("username")
        )

        while True:

            try:

                data = {
                    "timeout": 50,
                    "allowed_updates": ["message"]
                }

                if offset is not None:
                    data["offset"] = offset

                result = await telegram_request(
                    session,
                    "getUpdates",
                    data
                )

                if not result.get("ok"):
                    print("Telegram API error:", result)
                    await asyncio.sleep(5)
                    continue

                updates = result.get("result", [])

                for update in updates:

                    # Confirm this update
                    offset = update["update_id"] + 1

                    try:
                        await process_update(
                            session,
                            update
                        )

                    except Exception as e:
                        print(
                            "UPDATE ERROR:",
                            repr(e)
                        )

            except asyncio.CancelledError:
                raise

            except Exception as e:

                print(
                    "MAIN LOOP ERROR:",
                    repr(e)
                )

                await asyncio.sleep(5)


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    asyncio.run(main())
