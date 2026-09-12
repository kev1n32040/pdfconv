"""Видео → кружочек (video note) через ffmpeg."""
import asyncio
import shutil
from pathlib import Path

MAX_NOTE_SECONDS = 60  # Telegram ограничивает кружочки 60 секундами


async def video_to_note(src: Path, dst: Path) -> None:
    """
    Конвертирует видео в формат кружочка:
    квадрат 384x384, обрезка по центру, макс. 60 секунд, h264 + no audio track issues.
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg не установлен на сервере")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-t", str(MAX_NOTE_SECONDS),
        # кроп до квадрата по центру + масштаб до 384x384
        "-vf", "crop='min(iw,ih)':'min(iw,ih)',scale=384:384",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
        "-c:a", "aac", "-b:a", "64k",
        "-movflags", "+faststart",
        str(dst),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0 or not dst.exists() or dst.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg error: {stderr.decode()[-500:]}")
