# Чтобы pydub и yt-dlp находили ffmpeg/ffprobe в контейнере (Railway и т.д.)
import os
os.environ["PATH"] = "/usr/bin:" + os.environ.get("PATH", "")

from run import Bot
from utils import asyncio


async def main():
    await Bot.initialize()
    await Bot.run()


asyncio.run(main())
