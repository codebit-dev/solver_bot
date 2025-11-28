import os
import io
import logging
from dotenv import load_dotenv
from PIL import Image

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

from google import genai
from google.genai import types as genai_types


# ---------------- ENV ----------------
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BOT_USERNAME = os.getenv("BOT_USERNAME")  # without @


# ---------------- LOG ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------- GEMINI CLIENT ----------------
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-2.0-flash"


# ---------------- MASTER PROMPT ----------------
PROMPT = """
You are an exam-solving AI.

Your task:
- Extract the questions.
- Detect the marks (1m, 2m, 5m, 10m, 15m).
- Answer strictly according to marks.

Formatting Rules:
- 1 mark → One-line answer.
- 2 marks → 2–3 lines.
- 5 marks → Medium answer (8–12 lines).
- 10–15 marks → Detailed long answer with points.
- Maintain numbering.
- No greetings.
- No extra sentences.
- Only answers.
""".strip()


# ---------------- CLEAN TELEGRAM OUTPUT ----------------
def format_answer(ans):
    ans = ans.strip()

    # Replace any unicode bullets with Telegram-safe bullets
    ans = ans.replace("•", "-")
    ans = ans.replace("●", "-")
    ans = ans.replace("▪", "-")

    # Clean extra blank lines
    while "\n\n\n" in ans:
        ans = ans.replace("\n\n\n", "\n\n")

    return ans


# ---------------- IMAGE CONVERT ----------------
def to_jpeg(img_bytes):
    try:
        img = Image.open(io.BytesIO(img_bytes))
        rgb = img.convert("RGB")
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG")
        return buf.getvalue()
    except Exception:
        return img_bytes


# ---------------- SOLVE TEXT ----------------
def solve_text(text):
    response = client.models.generate_content(
        model=MODEL,
        contents=[PROMPT, text],
        config=genai_types.GenerateContentConfig(
            max_output_tokens=4000,
            temperature=0.2
        )
    )
    return response.text


# ---------------- SOLVE IMAGE ----------------
def solve_image(img_bytes):
    img_bytes = to_jpeg(img_bytes)

    image_part = genai_types.Part.from_bytes(
        data=img_bytes,
        mime_type="image/jpeg"
    )

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            image_part,
            PROMPT,
            "Extract the text from this question paper image and answer according to marks."
        ],
        config=genai_types.GenerateContentConfig(
            max_output_tokens=4000,
            temperature=0.2
        )
    )

    return response.text


# ---------------- HANDLERS ----------------
async def start(update: Update, context):
    await update.message.reply_text(
        "Send text or image of your question paper.\n"
        "In groups: mention me @{} or use /solve.".format(BOT_USERNAME)
    )


async def solve_cmd(update: Update, context):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Usage: /solve <questions>")
        return

    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    ans = solve_text(text)
    formatted = format_answer(ans)

    await update.message.reply_text(formatted)


async def handle_text(update: Update, context):
    text = update.message.text or ""

    # Only respond in group when mentioned
    if update.message.chat.type in ["group", "supergroup"]:
        if f"@{BOT_USERNAME}" not in text:
            return
        text = text.replace(f"@{BOT_USERNAME}", "").strip()

    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    ans = solve_text(text)
    formatted = format_answer(ans)

    await update.message.reply_text(formatted)


async def handle_image(update: Update, context):
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        img_bytes = await file.download_as_bytearray()

        await context.bot.send_chat_action(update.effective_chat.id, "typing")

        ans = solve_image(img_bytes)
        formatted = format_answer(ans)

        await update.message.reply_text(formatted)

    except Exception as e:
        print("IMAGE ERROR:", e)
        await update.message.reply_text("Image processing failed.")


# ---------------- MAIN APP ----------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("solve", solve_cmd))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
