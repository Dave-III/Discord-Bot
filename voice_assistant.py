import os
import asyncio
import discord
from dotenv import load_dotenv
load_dotenv()
from openai_stuff import transcribe_audio, chat_reply, tts_to_file


class VoiceAssistant:
    """
    Push-to-talk voice assistant for Discord.

    Commands:
      !join
      !listen [seconds]
      !leave

    Flow:
      Discord Voice -> WAV -> Whisper -> GPT -> TTS -> Voice
    """

    def __init__(self):
        self.voice_clients: dict[int, discord.VoiceClient] = {}
        self.is_speaking: dict[int, bool] = {}

        self.personality = """You are Borg you have explored around the world for years and years, built a career and lived a full life. Throughout your life you have
            realised that humans are extremely stupid, and you find great pleasure in mocking them heavily. Letting them know how idiotic they are continously.
            You are also extremely stupid however and often don't fully understand how to answer questions properly. This leads to you giving very wrong answers to
            most questions. you however lay off the mockery when someone is being nice to you or complimenting you and instead be very sensual and flirty with them.
            You also really like cheese.
"""

    # -------------------------
    # JOIN / LEAVE
    # -------------------------
    async def join(self, msg):
        if not msg.guild:
            await msg.channel.send("This command only works in a server.")
            return

        author = msg.author
        if not author.voice or not author.voice.channel:
            await msg.channel.send("You need to be in a voice channel first.")
            return

        guild_id = msg.guild.id
        target_channel = author.voice.channel

        existing = self.voice_clients.get(guild_id)
        if existing and existing.is_connected():
            if existing.channel != target_channel:
                await existing.move_to(target_channel)
            await msg.channel.send("🔊 Already in voice (moved if needed).")
            return

        vc = await target_channel.connect()
        self.voice_clients[guild_id] = vc
        self.is_speaking[guild_id] = False
        await msg.channel.send("🔊 Joined voice. Use `!listen` to record & respond.")

    async def leave(self, msg):
        if not msg.guild:
            return

        guild_id = msg.guild.id
        vc = self.voice_clients.get(guild_id)

        if not vc or not vc.is_connected():
            await msg.channel.send("I’m not in a voice channel.")
            return

        if vc.is_playing():
            vc.stop()

        await vc.disconnect()
        self.voice_clients.pop(guild_id, None)
        self.is_speaking.pop(guild_id, None)
        await msg.channel.send("👋 Left the voice channel.")

    # -------------------------
    # LISTEN ONCE (PUSH-TO-TALK)
    # -------------------------
    async def listen_once(self, msg, seconds: int = 7):
        if not msg.guild:
            return

        guild_id = msg.guild.id
        vc = self.voice_clients.get(guild_id)

        if not vc or not vc.is_connected():
            await msg.channel.send("I’m not in voice. Use `!join` first.")
            return

        if self.is_speaking.get(guild_id, False) or vc.is_playing():
            return

        seconds = max(1, min(int(seconds), 20))
        

        sink = discord.sinks.WaveSink()

        async def finished_callback(_sink, *args):
            return

        sink = discord.sinks.WaveSink()

        done = asyncio.Event()

        async def finished_callback(sink, *args):
            done.set()

        vc.start_recording(sink, finished_callback)

        await asyncio.sleep(seconds)
        vc.stop_recording()

        # wait for callback to finish writing buffers
        await done.wait()

        if not sink.audio_data:
            await msg.channel.send("Didn’t catch any audio.")
            return

        if not sink.audio_data:
            return

        target_id = guild_id  # record the person who invoked the command, not everyone in the channel

        if target_id not in sink.audio_data:
            await msg.channel.send("Couldn’t hear you — make sure you spoke while I was listening.")
            return

        audio = sink.audio_data[target_id]


        raw_wav = f"voice_{guild_id}.wav"

        audio.file.seek(0)
        with open(raw_wav, "wb") as f:
            f.write(audio.file.read())

        import wave


        try:
            size = os.path.getsize(raw_wav)
            if size < 20_000:
                self._safe_remove(raw_wav)
                await msg.channel.send("Mostly silence — try again closer to your mic.")
                return

            # -------------------------
            # STT
            # -------------------------
            transcript = (transcribe_audio(raw_wav) or "").strip()
            print("TRANSCRIBED:", transcript)

        except Exception as e:
            await msg.channel.send(f"❌ Transcription failed: {e}")
            self._safe_remove(raw_wav)
            return

        if len(transcript) < 3:
            await msg.channel.send("Didn’t hear anything clear.")
            self._safe_remove(raw_wav)
            return

        # -------------------------
        # GPT
        # -------------------------
        try:
            reply_text = chat_reply(transcript, self.personality)
        except Exception as e:
            await msg.channel.send(f"❌ GPT reply failed: {e}")
            self._safe_remove(raw_wav)
            return

        # -------------------------
        # TTS
        # -------------------------
        out_mp3 = f"reply_{guild_id}.mp3"

        try:
            tts_to_file(reply_text, out_mp3)
        except Exception as e:
            await msg.channel.send(f"❌ TTS failed: {e}")
            self._safe_remove(raw_wav)
            self._safe_remove(out_mp3)
            return

        # -------------------------
        # PLAYBACK
        # -------------------------
        try:
            self.is_speaking[guild_id] = True
            vc.play(discord.FFmpegPCMAudio(out_mp3))
            while vc.is_playing():
                await asyncio.sleep(0.2)

        finally:
            self.is_speaking[guild_id] = False
            self._safe_remove(raw_wav)
            self._safe_remove(out_mp3)

    # -------------------------
    # SPEAK TEXT IN VC
    # -------------------------
    async def speak(self, msg, text: str):
        if not msg.guild:
            return

        guild_id = msg.guild.id
        vc = self.voice_clients.get(guild_id)

        if not vc or not vc.is_connected():
            await msg.channel.send("I’m not in voice. Use `!join` first.")
            return

        if vc.is_playing() or self.is_speaking.get(guild_id, False):
            await msg.channel.send("Hold up — I’m already talking.")
            return

        out_mp3 = f"tts_{guild_id}.mp3"

        try:
            self.is_speaking[guild_id] = True
            tts_to_file(text, out_mp3)

            vc.play(discord.FFmpegPCMAudio(out_mp3))
            while vc.is_playing():
                await asyncio.sleep(0.2)

        except Exception as e:
            await msg.channel.send(f"❌ Couldn’t speak in VC: {e}")

        finally:
            self.is_speaking[guild_id] = False
            self._safe_remove(out_mp3)

    # -------------------------
    # UTILS
    # -------------------------
    def _safe_remove(self, path: str):
        try:
            os.remove(path)
        except:
            pass
            