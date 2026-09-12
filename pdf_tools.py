"""PDF-операции: сжатие (даунскейл картинок + recompress) и склейка."""
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def compress_pdf(src: Path, dst: Path, dpi: int = 120) -> tuple[int, int]:
    """Сжимает PDF, уменьшая изображения. Возвращает (размер_до, размер_после)."""
    reader = PdfReader(str(src))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    try:
        for page in writer.pages:
            for img in page.images:
                img.replace(img.image, quality=60)
    except Exception:
        pass  # если картинки не пережимаются — отдаём как есть
    with open(dst, "wb") as f:
        writer.write(f)
    return src.stat().st_size, dst.stat().st_size


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


def human_size(n: int) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024 or unit == "ГБ":
            return f"{n:.1f} {unit}" if unit != "Б" else f"{n} {unit}"
        n /= 1024
    return f"{n} Б"
