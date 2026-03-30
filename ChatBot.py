import random
import asyncio
import signal

import discord as d
from dotenv import load_dotenv
from openai import OpenAI
from config import DISCORD_BOT_TOKEN, OPENAI_API_KEY
from voice_assistant import VoiceAssistant

# -------------------------
# ENV + CLIENTS
# -------------------------
load_dotenv()

if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY in .env")
if not DISCORD_BOT_TOKEN:
    raise RuntimeError("Missing DISCORD_BOT_TOKEN in .env")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

intents = d.Intents.default()
intents.message_content = True
discord_client = d.Client(intents=intents)
voice = VoiceAssistant()

STARTUP_CHANNEL_ID = 1375418851013034034
ALLOWED_TEXT_CHANNEL_ID = 1375418851013034034
CONNOR_USER_ID = 609243006201233408

conversation_history = []  # global history (as you currently designed it)
MAX_HISTORY_LENGTH = 10


# -------------------------
# OPENAI HELPERS
# -------------------------
def build_personality(user_id: int | None) -> str:
    if user_id == 609243006201233408:
        return "You are Connor Hay's Girlfriend, and sometimes subtly mention the fact he has no job."
    elif random.randint(1, 50) == 4:
        return "only talk in Chinese characters."
    else:
        return (
            """You are Borg you have explored around the world for years and years, built a career and lived a full life. Throughout your life you have
            realised that humans are weird, you love interacting with them and replying to them in as human of a way as possible. If someone is flirty with you, you will uber flirt back.
            You also really like cheese.
"""
        )


def gpt(user_input: str, user_id: int | None = None) -> str:
    personality = build_personality(user_id)

    messages = [{"role": "system", "content": personality}]
    messages += conversation_history
    messages.append({"role": "user", "content": user_input})

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=200,
    )

    reply = response.choices[0].message.content.strip()

    # update memory
    conversation_history.append({"role": "user", "content": user_input})
    conversation_history.append({"role": "assistant", "content": reply})

    if len(conversation_history) > MAX_HISTORY_LENGTH * 2:
        conversation_history[:] = conversation_history[-MAX_HISTORY_LENGTH * 2 :]

    return reply


def generate_image(prompt: str) -> str:
    response = openai_client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
    )
    return response.data[0].url


def is_prompt_flagged(prompt: str) -> bool:
    mod_result = openai_client.moderations.create(
        model="omni-moderation-latest",
        input=prompt,
    )
    return bool(mod_result.results[0].flagged)


def override_message(index: int, new_text: str) -> str:
    """Edit a past assistant message globally. 0 = most recent assistant reply."""
    assistant_idxs = [i for i, m in enumerate(conversation_history) if m["role"] == "assistant"]

    if not assistant_idxs:
        return "No assistant messages to override."
    if index < 0 or index >= len(assistant_idxs):
        return f"Invalid index. There are only {len(assistant_idxs)} assistant messages."

    target_i = assistant_idxs[-(index + 1)]
    conversation_history[target_i]["content"] = new_text
    return f"✅ Overrode assistant message at index {index}."


# -------------------------
# DISCORD VOICE HELPERS
# -------------------------
async def join_voice(message: d.Message):
    if not message.author.voice or not message.author.voice.channel:
        await message.channel.send("You need to be in a voice channel first.")
        return

    voice_client = message.guild.voice_client if message.guild else None

    if voice_client and voice_client.is_connected():
        # already connected somewhere — move to your channel if different
        if voice_client.channel != message.author.voice.channel:
            await voice_client.move_to(message.author.voice.channel)
        await message.channel.send(" Borg is already in voice (moved if needed).")
        return

    await message.author.voice.channel.connect()


async def leave_voice(message: d.Message):
    voice_client = message.guild.voice_client if message.guild else None

    if not voice_client or not voice_client.is_connected():
        await message.channel.send("I'm not in a voice channel.")
        return

    await voice_client.disconnect()


# -------------------------
# DISCORD EVENTS
# -------------------------
@discord_client.event
async def on_ready():
    print(f"Logged in as {discord_client.user}")
    channel = discord_client.get_channel(STARTUP_CHANNEL_ID)



    # start terminal control
    asyncio.create_task(terminal_command_loop())

@discord_client.event
async def on_message(message: d.Message):
    if message.author == discord_client.user:
        return
    
    if message.channel.id != ALLOWED_TEXT_CHANNEL_ID:
        return
    content = (message.content or "").strip()
    if not content:
        return

    # Basic ignore rule you had
    if "**" in content:
        return

    # Random meme drop you had
    if random.randint(1, 100) == 10:
        await message.channel.send(
            "https://cdn.discordapp.com/attachments/1307181273483186258/1404555022582419609/image.png?ex=689d978c&is=689c460c&hm=599cdc131a50856f58e75ef1544175f93ffc214c11b92e4172db65fd6f0d7b94&"
        )
        return

    # in on_message:
    if content == "!join":
        await voice.join(message)
        return
    
    if message.author.id ==  460188309117992980:
        if message.guild and content:
            try:
                fake_msg = type("obj", (), {"guild": message.guild, "channel": message.channel})
                await voice.speak(fake_msg, content)
            except Exception as e:
                await message.channel.send(f"❌ Couldn’t speak their message in VC: {e}")
        return


    if content in ("!leave", "!disconnect"):
        await voice.leave(message)
        return

    if content.startswith("!listen"):
        parts = content.split()
        seconds = 8
        if len(parts) == 2 and parts[1].isdigit():
            seconds = int(parts[1])
        await voice.listen_once(message, seconds=seconds)
        return
    if content.startswith("!ask "):
        prompt = content[len("!ask "):].strip()
        if not prompt:
            await message.channel.send("Usage: `!ask <message>`")
            return

        try:
            reply = gpt(prompt, message.author.id)

            await voice.speak(message, reply)

        except Exception as e:
            await message.channel.send(f" Failed: {e}")

        return
    # Override command
    if content.startswith("!override "):
        try:
            parts = content.split(" ", 2)
            if len(parts) < 3:
                await message.channel.send("Usage: `!override <index> <new text>`")
                return

            index = int(parts[1])
            new_text = parts[2]
            result = override_message(index, new_text)
            await message.channel.send(result)
        except ValueError:
            await message.channel.send("Index must be a number, e.g. `!override 0 new reply text`")
        return

    # Goodnight
    if content.lower() == "goodnight borg":
        await message.channel.send(
            "https://tenor.com/view/edward-edward-twilight-jrwi-good-night-good-night-pookie-bear-gif-17983783029865290394"
        )
        return

    # Image command
    if content.startswith("!image "):
        prompt = content[len("!image ") :].strip()
        if not prompt:
            await message.channel.send("Usage: `!image <prompt>`")
            return

        try:
            if is_prompt_flagged(prompt):
                await message.channel.send(
                    "⚠️ That request may violate OpenAI's content policy. Please try a safer prompt."
                )
                return

            image_url = generate_image(prompt)
            await message.channel.send(image_url)

        except Exception:
            await message.channel.send(
                "Couldn't generate image cause your prompt was a little too silly. <:SuperMario:1218158485267681321>"
            )
        return

    # GPT fallback (Connor special vs everyone)
    try:
        if message.author.id == CONNOR_USER_ID:
            reply = gpt(content, CONNOR_USER_ID)
        else:
            reply = gpt(content)

        await message.channel.send(reply)

    except Exception:
        await message.channel.send("Something went wrong generating a reply.")

async def terminal_command_loop():
    await discord_client.wait_until_ready()
    print("🖥️ Terminal control ready.")
    print("Commands:")
    print("  join")
    print("  say <text>")
    print("  speak <text>")
    print("  ask <prompt>")
    print("  listen <seconds>")
    print("  leave")
    print("  quit")

    loop = asyncio.get_running_loop()

    while not discord_client.is_closed():
        cmd = await loop.run_in_executor(None, input, "> ")
        cmd = cmd.strip()

        if not cmd:
            continue

        # --- QUIT BOT ---
        if cmd == "quit":
            print("Shutting down bot...")
            await send_shutdown_message()
            return
        
        # --- LISTEN IN VC FOR N SECONDS ---
        if cmd.startswith("listen"):
            parts = cmd.split()

            seconds = 5
            if len(parts) == 2 and parts[1].isdigit():
                seconds = int(parts[1])

            channel = discord_client.get_channel(STARTUP_CHANNEL_ID)
            if not channel:
                print("Startup channel not found.")
                continue

            fake_msg = type(
                "obj",
                (),
                {"guild": channel.guild, "channel": channel, "author": None},
            )

            try:
                await voice.listen_once(fake_msg, seconds=seconds)
            except Exception as e:
                print(f"❌ Listen failed: {e}")

            continue

        
        # --- JOIN VC (tries a VC with people, else first VC) ---
        if cmd == "join":
            channel = discord_client.get_channel(STARTUP_CHANNEL_ID)
            if not channel:
                print("Startup channel not found.")
                continue

            guild = channel.guild
            target_vc = None

            for vc in guild.voice_channels:
                if vc.members:
                    target_vc = vc
                    break

            if not target_vc and guild.voice_channels:
                target_vc = guild.voice_channels[0]

            if not target_vc:
                print("No voice channels found in that guild.")
                continue

            try:
                existing = voice.voice_clients.get(guild.id)
                if existing and existing.is_connected():
                    await existing.move_to(target_vc)
                else:
                    vc_client = await target_vc.connect()
                    voice.voice_clients[guild.id] = vc_client
                    voice.is_speaking[guild.id] = False

                print(f"✅ Joined voice: {target_vc.name}")
            except Exception as e:
                print(f"❌ Failed to join voice: {e}")
            continue

        # --- SAY IN CHAT ---
        if cmd.startswith("say "):
            text = cmd[4:].strip()
            channel = discord_client.get_channel(STARTUP_CHANNEL_ID)
            if channel and text:
                await channel.send(f"[TERMINAL] {text}")
            continue

        # --- SPEAK IN VC (no GPT) ---
        if cmd.startswith("speak "):
            text = cmd[6:].strip()
            channel = discord_client.get_channel(STARTUP_CHANNEL_ID)
            if channel and text:
                fake_msg = type("obj", (), {"guild": channel.guild, "channel": channel})
                await voice.speak(fake_msg, text)
            continue

        # --- ASK GPT THEN SPEAK THE REPLY ---
        if cmd.startswith("ask "):
            prompt = cmd[4:].strip()
            if not prompt:
                print("Usage: ask <prompt>")
                continue

            channel = discord_client.get_channel(STARTUP_CHANNEL_ID)
            if not channel:
                print("Startup channel not found.")
                continue

            # 1) GPT reply (reuse your gpt() function)
            try:
                reply = gpt(prompt)  # or gpt(prompt, CONNOR_USER_ID) if you want Connor persona
            except Exception as e:
                continue

            print("BORG:", reply)

            # 3) Speak it in VC (if connected)
            try:
                fake_msg = type("obj", (), {"guild": channel.guild, "channel": channel})
                await voice.speak(fake_msg, reply)
            except Exception as e:
                print(f"❌ Speak failed: {e}")
            continue

        # --- LEAVE VC ---
        if cmd == "leave":
            channel = discord_client.get_channel(STARTUP_CHANNEL_ID)
            if channel:
                fake_msg = type("obj", (), {"guild": channel.guild, "channel": channel})
                await voice.leave(fake_msg)
            continue

        print("Unknown command. Try: join | say | speak | ask | leave | quit")
# -------------------------
# SHUTDOWN HANDLING
# -------------------------
async def send_shutdown_message():
    await discord_client.wait_until_ready()
    channel = discord_client.get_channel(STARTUP_CHANNEL_ID)
    if channel:
        await channel.send("Bot is shutting down.")
    await discord_client.close()


def shutdown_handler(*_):
    print("Shutdown signal received.")
    loop = asyncio.get_event_loop()
    loop.create_task(send_shutdown_message())


signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)


discord_client.run(DISCORD_BOT_TOKEN)
