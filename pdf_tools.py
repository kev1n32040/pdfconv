"""PDF-операции: сжатие через Ghostscript (с фолбэком на pypdf) и склейка."""
import asyncio
import shutil
from pathlib import Path

from pypdf import PdfReader, PdfWriter

# Пресеты Ghostscript: PDFSETTINGS + DPI картинок
GS_PRESETS = {
    "low": ("screen", 72),     # максимальное сжатие, для экрана
    "medium": ("ebook", 150),  # баланс
    "high": ("printer", 300),  # почти без потерь
}
DEFAULT_PRESET = "medium"


def merge_pdfs(sources: list[Path], dst: Path) -> int:
    """Склеивает несколько PDF в один. Возвращает число страниц."""
    writer = PdfWriter()
    total = 0
    for src in sources:
        reader = PdfReader(str(src))
        for page in reader.pages:
            writer.add_page(page)
            total += 1
    with open(dst, "wb") as f:
        writer.write(f)
    return total


async def compress_pdf(src: Path, dst: Path, preset: str = DEFAULT_PRESET) -> tuple[int, int]:
    """Сжимает PDF через Ghostscript; если его нет — фолбэк на pypdf."""
    if shutil.which("gs"):
        await _compress_gs(src, dst, preset)
    else:
        await asyncio.to_thread(_compress_pypdf, src, dst)
    return src.stat().st_size, dst.stat().st_size


async def _compress_gs(src: Path, dst: Path, preset: str) -> None:
    gs_preset, dpi = GS_PRESETS.get(preset, GS_PRESETS[DEFAULT_PRESET])
    cmd = [
        "gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
        f"-dPDFSETTINGS=/{gs_preset}",
        f"-dColorImageResolution={dpi}",
        f"-dGrayImageResolution={dpi}",
        f"-dMonoImageResolution={dpi}",
        "-dNOPAUSE", "-dQUIET", "-dBATCH",
        f"-sOutputFile={dst}", str(src),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0 or not dst.exists() or dst.stat().st_size == 0:
        raise RuntimeError(f"ghostscript: {stderr.decode()[-300:]}")


def _compress_pypdf(src: Path, dst: Path) -> None:
    """Фолбэк без Ghostscript: пережимает только JPEG-картинки."""
    reader = PdfReader(str(src))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    try:
        for page in writer.pages:
            for img in page.images:
                img.replace(img.image, quality=60)
    except Exception:
        pass
    with open(dst, "wb") as f:
        writer.write(f)


def human_size(n: int) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024 or unit == "ГБ":
            return f"{n:.1f} {unit}" if unit != "Б" else f"{n} {unit}"
        n /= 1024
    return f"{n} Б"
