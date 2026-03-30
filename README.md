# Borg Discord Bot

This Discord bot is powered by the openAI API, with Text Chat and Voice Assistant Features. It also has A custom UI that is controlled through the terminal.

## Features

- Context-aware text chat
- OpenAI-powered responses
- Voice channel support
- Speech-to-text and text-to-speech
- Configurable using a `.env` file
- AI Image Generation

## Tech Stack

- Python
- discord.py
- OpenAI API
- python-dotenv

## Project Structure
.
├── ChatBot.py `\n`
├── openai_stuff.py `\n`
├── voice_assistant.py `\n`
├── requirements.txt `\n`
├── .env `\n`
└── README.md `\n`

### Setup Custom `.env`

```env
DISCORD_BOT_TOKEN=
OPENAI_API_KEY=
STARTUP_CHANNEL_ID=
ALLOWED_TEXT_CHANNEL_ID=
OWNER_USER_ID=