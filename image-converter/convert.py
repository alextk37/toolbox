#!/usr/bin/env python3
"""
Конвертер изображений в JPEG — максимальное качество, минимальный расход ОЗУ.

Поддерживает: HEIC, HEIF, PNG, BMP, TIFF, WEBP, AVIF, GIF, ICO, PSD, SVG* и др.
Обрабатывает файлы строго по одному — не загружает в память ничего лишнего.

Зависимости (см. requirements.txt):
    pip install -r requirements.txt

Использование:
    python3 convert.py                          # input_images → output_images
    python3 convert.py -i ./мои_фото -o ./jpg   # свои папки
    python3 convert.py --quality 95
    python3 convert.py --recursive
    python3 convert.py --dry-run                # посмотреть что будет
    python3 convert.py --delete-originals       # удалить исходники после конвертации
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Проверка зависимостей — чтобы пользователь сразу увидел чего не хватает
# ---------------------------------------------------------------------------

MISSING = []

try:
    from PIL import Image, UnidentifiedImageError
except ImportError:
    MISSING.append(("Pillow", "pip install Pillow"))

try:
    import pillow_heif
except ImportError:
    MISSING.append(("pillow-heif", "pip install pillow-heif  (нужен для HEIC с iPhone)"))

try:
    from rich.console import Console
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
        MofNCompleteColumn,
    )
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.layout import Layout
    from rich.columns import Columns
    from rich.rule import Rule
    from rich import box
    from rich.live import Live
    from rich.style import Style
    from rich.align import Align
    from rich.tree import Tree
except ImportError:
    MISSING.append(("rich", "pip install rich"))

if MISSING:
    # Без Rich выводим простой текст
    print("\n  НЕ ХВАТАЕТ БИБЛИОТЕК:\n")
    for name, cmd in MISSING:
        print(f"    ✗  {name:15} →  {cmd}")
    print("\n  Установите одной командой:\n")
    print("    pip install Pillow pillow-heif rich\n")
    sys.exit(1)

# Регистрируем HEIF-поддержку в Pillow (добавляет .heic/.heif в список форматов)
pillow_heif.register_heif_opener()

# ---------------------------------------------------------------------------
# Консоль и стили
# ---------------------------------------------------------------------------

console = Console()

# Цветовая палитра
STYLE_OK = Style(color="green", bold=True)
STYLE_SKIP = Style(color="cyan", dim=True)
STYLE_FAIL = Style(color="red", bold=True)
STYLE_WARN = Style(color="yellow")
STYLE_PATH = Style(color="bright_blue")
STYLE_SIZE = Style(color="cyan")
STYLE_DIM = Style(color="bright_black")
STYLE_HEADER = Style(color="bright_white", bold=True)
STYLE_NUMBER = Style(color="bright_green", bold=True)
STYLE_DELTA = Style(color="green")
STYLE_FILE = Style(color="white")

# Эмодзи-индикаторы
ICON_OK = "✓"
ICON_SKIP = "⊘"
ICON_FAIL = "✗"
ICON_WARN = "⚠"
ICON_DELETE = "🗑"
ICON_FOLDER = "📁"
ICON_IMAGE = "🖼"
ICON_CLOCK = "⏱"
ICON_DISK = "💾"
ICON_GEAR = "⚙"

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {
    ".heic", ".heif", ".heifs",
    ".png", ".jpg", ".jpeg", ".jfif",
    ".bmp", ".dib",
    ".tiff", ".tif",
    ".webp",
    ".avif",
    ".gif",
    ".ico", ".cur",
    ".psd", ".psb",
    ".tga", ".icb", ".vda", ".vst",
    ".pcx",
    ".ppm", ".pgm", ".pbm", ".pnm",
    ".svg", ".svgz",
    ".eps",
    ".jp2", ".j2k", ".jpf", ".jpx",
    ".dds",
    ".blp",
    ".fits", ".fit",
    ".im", ".ftc", ".ftu",
    ".msp",
    ".sgi", ".rgb", ".rgba", ".bw",
    ".xbm",
}

SKIP_EXTENSIONS = {".jpg", ".jpeg", ".jfif", ".jpe"}

NON_IMAGE_EXTENSIONS = {
    ".txt", ".py", ".sh", ".md", ".json", ".yaml", ".toml",
    ".ini", ".cfg", ".log", ".csv", ".xml", ".html", ".css",
    ".js", ".ts", ".mp4", ".mov", ".avi", ".mkv", ".mp3", ".wav",
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar",
    ".xlsx", ".docx", ".pptx", ".db", ".sqlite",
}

DEFAULT_QUALITY = 100
MB = 1024 * 1024


# ---------------------------------------------------------------------------
# Утилиты форматирования
# ---------------------------------------------------------------------------

def format_size(size_bytes: int) -> str:
    """Человекочитаемый размер файла."""
    if size_bytes >= MB:
        return f"{size_bytes / MB:.1f} МБ"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} КБ"
    return f"{size_bytes} Б"


def size_delta(before: int, after: int) -> str:
    """Разница размеров в человекочитаемом виде со знаком."""
    delta = before - after
    if delta > 0:
        return f"-{format_size(delta)}"
    elif delta < 0:
        return f"+{format_size(-delta)}"
    return "±0"


def format_duration(seconds: float) -> str:
    """Форматирует длительность."""
    if seconds < 60:
        return f"{seconds:.1f} сек"
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins} мин {secs:.0f} сек"


# ---------------------------------------------------------------------------
# Сбор файлов
# ---------------------------------------------------------------------------

def collect_files(root: Path, recursive: bool) -> list[Path]:
    """Собирает список ВСЕХ изображений (включая JPEG — они будут скопированы)."""
    files: list[Path] = []
    iterator = root.rglob("*") if recursive else root.glob("*")

    for p in iterator:
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in SUPPORTED_EXTENSIONS or ext in SKIP_EXTENSIONS or ext not in NON_IMAGE_EXTENSIONS:
            files.append(p)

    return files


def peek_image(src: Path) -> dict:
    """Читает заголовок изображения (без загрузки пикселей). Возвращает метаданные."""
    try:
        img = Image.open(src)
        mode = img.mode
        w, h = img.size
        size = src.stat().st_size
        img.close()
        return {"mode": mode, "width": w, "height": h, "size": size, "ok": True}
    except Exception:
        return {"mode": "?", "width": 0, "height": 0, "size": src.stat().st_size, "ok": False}


# ---------------------------------------------------------------------------
# Конвертация одного файла
# ---------------------------------------------------------------------------

def convert_one(src: Path, dst: Path, quality: int) -> dict:
    """
    Конвертирует ОДНО изображение в JPEG.
    В ОЗУ — только текущая картинка. После сохранения память освобождается.
    """
    result = {
        "src": src,
        "dst": dst,
        "ok": False,
        "skipped": False,
        "error": None,
        "size_before": 0,
        "size_after": 0,
        "mode": "?",
        "dimensions": "?×?",
    }

    try:
        result["size_before"] = src.stat().st_size
    except OSError:
        pass

    if dst.exists():
        result["skipped"] = True
        result["size_after"] = dst.stat().st_size
        return result

    img = None
    try:
        img = Image.open(src)
        result["mode"] = img.mode
        result["dimensions"] = f"{img.width}×{img.height}"

        # GIF: первый кадр
        if getattr(img, "is_animated", False):
            img.seek(0)

        # RGBA / P → RGB (JPEG не поддерживает прозрачность)
        if img.mode in ("RGBA", "LA", "PA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(
                img, (0, 0), img if img.mode in ("RGBA", "LA") else None
            )
            img.close()
            img = background

        elif img.mode in ("CMYK", "LAB", "HSV", "YCbCr"):
            img = img.convert("RGB")

        elif img.mode not in ("RGB", "L", "1"):
            img = img.convert("RGB")

        # Сохранение: качество 100, 4:4:4 (без субдискретизации цвета)
        img.save(
            dst,
            format="JPEG",
            quality=quality,
            subsampling=0,
            optimize=True,
            progressive=False,
        )

        result["ok"] = True
        result["size_after"] = dst.stat().st_size

    except UnidentifiedImageError:
        result["error"] = "не удалось распознать формат"
    except OSError as e:
        result["error"] = f"ошибка ввода/вывода: {e}"
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    finally:
        if img is not None:
            try:
                img.close()
            except Exception:
                pass

    return result


def delete_original(src: Path) -> bool:
    """Удаляет исходный файл. Возвращает True если успешно."""
    try:
        src.unlink()
        return True
    except OSError:
        return False


def copy_file(src: Path, dst: Path) -> dict:
    """Копирует JPEG-файл (без перекодировки — побайтово)."""
    import shutil
    result = {
        "src": src, "dst": dst, "ok": True, "skipped": False,
        "error": None, "size_before": src.stat().st_size, "size_after": 0,
        "mode": "JPEG", "dimensions": "?×?",
    }
    if dst.exists():
        result["skipped"] = True
        result["size_after"] = dst.stat().st_size
        return result
    try:
        shutil.copy2(src, dst)
        result["size_after"] = dst.stat().st_size
    except OSError as e:
        result["ok"] = False
        result["error"] = f"ошибка копирования: {e}"
    return result


# ---------------------------------------------------------------------------
# Rich-интерфейс
# ---------------------------------------------------------------------------

def build_header(quality: int, input_dir: str, output_dir: str, recursive: bool) -> Panel:
    """Панель-заголовок с настройками конвертации."""
    settings = Text()
    settings.append("Качество JPEG: ", style=STYLE_DIM)
    settings.append(f"{quality}", style=STYLE_NUMBER)
    settings.append("  •  ")
    settings.append("Субдискретизация: ", style=STYLE_DIM)
    settings.append("4:4:4", style=STYLE_OK)
    settings.append("  •  ")
    settings.append("Режим: ", style=STYLE_DIM)
    settings.append("рекурсивный" if recursive else "плоский", style=STYLE_PATH)

    title = Text("КОНВЕРТЕР ИЗОБРАЖЕНИЙ → JPEG", style=STYLE_HEADER)

    paths = Text()
    paths.append(f"{ICON_FOLDER}  Вход:  ", style=STYLE_DIM)
    paths.append(input_dir, style=STYLE_PATH)
    paths.append("\n")
    paths.append(f"{ICON_FOLDER}  Выход: ", style=STYLE_DIM)
    paths.append(output_dir, style=STYLE_PATH)

    body = Text.assemble(paths, "\n\n", settings)
    return Panel(body, title=title, border_style="bright_blue", box=box.ROUNDED, padding=(1, 2))


def build_dry_run_table(files: list[Path]) -> Table:
    """Таблица предпросмотра (dry-run)."""
    table = Table(
        title=Text("ПРЕДПРОСМОТР — файлы НЕ изменяются", style=STYLE_WARN),
        box=box.ROUNDED,
        border_style="dim blue",
        header_style="bold cyan",
        show_lines=False,
        expand=True,
    )
    table.add_column("№", style="dim", width=4, justify="right")
    table.add_column("Файл", style="white", no_wrap=False)
    table.add_column("Размер", style="cyan", justify="right", width=10)
    table.add_column("Режим", style="dim", width=6)
    table.add_column("Разрешение", style="dim", justify="right", width=12)
    table.add_column("Тип", style="yellow", width=6)
    table.add_column("Статус", style="dim", width=12)

    total_size = 0
    recognized = 0
    unrecognized = 0

    for i, src in enumerate(files, 1):
        meta = peek_image(src)
        ext = src.suffix.lower()
        size_str = format_size(meta["size"]) if meta["size"] else "?"
        dims = f"{meta['width']}×{meta['height']}" if meta["ok"] else "?"
        mode = meta["mode"] if meta["ok"] else "?"
        is_jpeg = ext in SKIP_EXTENSIONS
        status = "[dim]копия[/dim]" if is_jpeg else "ок" if meta["ok"] else "[red]неизв.[/red]"

        total_size += meta["size"]
        if meta["ok"]:
            recognized += 1
        else:
            unrecognized += 1

        table.add_row(
            str(i), src.name, size_str, mode, dims, ext.upper().lstrip("."), status
        )

    # Итоговая строка
    footer = Text()
    footer.append(f"{len(files)} файлов  •  ", style=STYLE_NUMBER)
    footer.append(f"~{format_size(total_size)}  •  ", style=STYLE_SIZE)
    footer.append(f"{recognized} распознано", style=STYLE_OK)
    if unrecognized:
        footer.append(f"  •  {unrecognized} не распознано", style=STYLE_FAIL)
    table.caption = footer
    return table


def build_summary_table(
    ok: int, copy: int, skip: int, fail: int,
    total_saved: int, deleted: int,
    elapsed: float, file_count: int,
    errors: list[tuple[str, str]],
) -> Panel:
    """Итоговая панель с результатами."""
    # Основная таблица
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 4), expand=False)
    table.add_column(style="dim")
    table.add_column(style="white")
    table.add_column(style="dim")

    table.add_row(f"{ICON_OK}  Сконвертировано", f"[bold green]{ok}[/bold green]", f"из {file_count}")
    if copy:
        table.add_row(f"{ICON_OK}  Скопировано (JPEG)", f"[bold cyan]{copy}[/bold cyan]", "без перекодировки")
    table.add_row(f"{ICON_SKIP}  Пропущено", f"[dim cyan]{skip}[/dim cyan]", "уже существуют")
    if fail:
        table.add_row(f"{ICON_FAIL}  Ошибок", f"[bold red]{fail}[/bold red]", "см. ниже")
    if total_saved > 0:
        table.add_row(f"{ICON_DISK}  Места на диске", f"[green]-{format_size(total_saved)}[/green]", "JPEG эффективнее исходников")
    if deleted:
        table.add_row(f"{ICON_DELETE}  Удалено исходников", f"[yellow]{deleted}[/yellow]", "")
    table.add_row(f"{ICON_CLOCK}  Время", format_duration(elapsed), "")

    # Секция с ошибками (если есть)
    error_block = None
    if errors:
        error_text = Text()
        for fname, err in errors:
            error_text.append(f"  {ICON_FAIL}  ", style=STYLE_FAIL)
            error_text.append(f"{fname}", style=STYLE_FILE)
            error_text.append(f"  →  {err}\n", style=STYLE_DIM)
        error_block = Panel(
            error_text,
            title="ОШИБКИ",
            border_style="red",
            box=box.ROUNDED,
            padding=(1, 2),
        )

    content = [Align.center(table)]
    if error_block:
        content.append(error_block)

    return Panel(
        Columns(content) if len(content) > 1 else content[0],
        title=Text("ГОТОВО", style=STYLE_HEADER),
        border_style="green",
        box=box.ROUNDED,
        padding=(1, 2),
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Конвертирует изображения в JPEG (макс. качество, экономно по ОЗУ)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python3 convert.py                          # input_images → output_images
  python3 convert.py -i ./фото -o ./jpg       # свои папки
  python3 convert.py --quality 95
  python3 convert.py --recursive
  python3 convert.py --dry-run
  python3 convert.py --delete-originals
        """,
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        default="input_images",
        help="Папка с исходными изображениями (по умолчанию: input_images)",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default="output_images",
        help="Папка для сконвертированных JPEG (по умолчанию: output_images)",
    )
    parser.add_argument("-q", "--quality", type=int, default=DEFAULT_QUALITY,
                        help=f"Качество JPEG (1–100, по умолчанию {DEFAULT_QUALITY})")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="Обрабатывать вложенные папки рекурсивно")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="Ничего не менять — просто показать что будет сконвертировано")
    parser.add_argument("-d", "--delete-originals", action="store_true",
                        help="Удалить исходные файлы после успешной конвертации")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Не спрашивать подтверждения")
    parser.add_argument("--no-color", action="store_true",
                        help="Отключить цвета (для логов)")

    args = parser.parse_args()

    if args.no_color:
        console.no_color = True

    # Валидация качества
    quality = max(1, min(100, args.quality))
    if quality != args.quality:
        console.print(
            f"  {ICON_WARN}  Качество скорректировано: {args.quality} → {quality}",
            style=STYLE_WARN,
        )

    # ── Входная папка ─────────────────────────────────────────────
    input_dir = Path(args.input).expanduser().resolve()

    if not input_dir.exists():
        console.print()
        console.print(Panel(
            Text.assemble(
                "Папка ", (str(input_dir), STYLE_PATH), " не существует.\n\n",
                ("Создайте её и положите туда изображения:\n", STYLE_DIM),
                ("  mkdir -p ", STYLE_DIM), (str(input_dir), STYLE_PATH),
            ),
            title=f"{ICON_FAIL}  ПАПКА НЕ НАЙДЕНА",
            border_style="red",
            box=box.ROUNDED,
            padding=(1, 2),
        ))
        console.print()
        sys.exit(1)

    if not input_dir.is_dir():
        console.print(Panel(
            Text.assemble(
                (str(input_dir), STYLE_PATH), " существует, но это не папка.",
            ),
            title=f"{ICON_FAIL}  НЕ ПАПКА",
            border_style="red",
            box=box.ROUNDED,
        ))
        sys.exit(1)

    # ── Выходная папка ────────────────────────────────────────────
    output_dir = Path(args.output).expanduser().resolve()

    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        console.print(
            f"  {ICON_FOLDER}  Создана папка для результатов: "
            f"[bright_blue]{output_dir}[/bright_blue]",
        )

    # ── Заголовок ─────────────────────────────────────────────────
    console.print()
    console.print(build_header(quality, str(input_dir), str(output_dir), args.recursive))

    # ── Сканирование ───────────────────────────────────────────────
    with console.status(
        f"[dim]Сканирую [bright_blue]{input_dir}[/bright_blue]…[/dim]",
        spinner="dots",
    ):
        files = collect_files(input_dir, args.recursive)

    if not files:
        console.print()
        console.print(Panel(
            "Папка пуста — нет файлов для обработки.",
            title="ПУСТО", border_style="yellow", box=box.ROUNDED,
        ))
        console.print()
        return

    # Считаем сколько JPEG (копировать) и сколько остальных (конвертировать)
    jpeg_files = [f for f in files if f.suffix.lower() in SKIP_EXTENSIONS]
    convert_files = [f for f in files if f.suffix.lower() not in SKIP_EXTENSIONS]

    console.print(
        f"  {ICON_IMAGE}  Всего изображений: [bold]{len(files)}[/bold]",
    )
    if jpeg_files:
        console.print(
            f"     Из них JPEG (скопировать): [dim cyan]{len(jpeg_files)}[/dim cyan]",
        )
    if convert_files:
        console.print(
            f"     Остальные (конвертировать): [bold green]{len(convert_files)}[/bold green]",
        )
    console.print()

    # ── Строим маппинг: исходный путь → выходной путь ─────────────
    # Сохраняем структуру вложенных папок при рекурсивном режиме
    file_pairs: list[tuple[Path, Path]] = []
    for src in files:
        rel = src.relative_to(input_dir)
        dst = output_dir / rel.with_suffix(".jpg")
        dst.parent.mkdir(parents=True, exist_ok=True)
        file_pairs.append((src, dst))

    # ── Dry-run: таблица предпросмотра ─────────────────────────────
    if args.dry_run:
        console.print(build_dry_run_table(files))
        console.print()
        console.print(f"  {ICON_GEAR}  Качество JPEG: [bold]{quality}[/bold]", style=STYLE_DIM)
        console.print(f"  {ICON_DELETE}  Удаление исходников: {'[yellow]да[/yellow]' if args.delete_originals else '[dim]нет[/dim]'}")
        console.print()
        return

    # ── Подтверждение удаления ─────────────────────────────────────
    if args.delete_originals and not args.yes:
        console.print(Panel(
            Text.assemble(
                "После конвертации ", (f"{len(files)}", STYLE_NUMBER),
                " исходных файлов будут ", ("УДАЛЕНЫ", STYLE_FAIL), ".",
            ),
            title=f"{ICON_WARN}  ВНИМАНИЕ", border_style="yellow", box=box.ROUNDED,
        ))
        answer = console.input("\n  Продолжить? [[y/N]]: ").strip().lower()
        if answer not in ("y", "yes", "д", "да"):
            console.print("  Отменено.", style=STYLE_DIM)
            return

    # ── Конвертация с Rich Progress ────────────────────────────────
    console.print(Rule(style="dim blue"))
    console.print(Text("КОНВЕРТАЦИЯ", style=STYLE_HEADER, justify="center"))
    if args.delete_originals:
        console.print(
            Text(f"{ICON_WARN}  Исходники будут удалены после конвертации", style=STYLE_WARN, justify="center")
        )
    console.print()

    ok_count = 0       # успешно сконвертировано
    copy_count = 0     # успешно скопировано (JPEG → JPEG)
    skip_count = 0
    fail_count = 0
    total_saved = 0
    deleted_count = 0
    errors: list[tuple[str, str]] = []
    start_time = time.monotonic()

    progress = Progress(
        SpinnerColumn(spinner_name="dots", style="dim cyan"),
        TextColumn("[progress.description]{task.description}", style="white"),
        BarColumn(bar_width=30, style="bright_blue", complete_style="green", finished_style="green"),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        console=console,
        expand=False,
    )

    with progress:
        task_id = progress.add_task("", total=len(files))

        for src, dst in file_pairs:
            fname = src.name
            display_name = fname if len(fname) <= 35 else f"…{fname[-34:]}"
            progress.update(task_id, description=display_name)

            is_jpeg = src.suffix.lower() in SKIP_EXTENSIONS

            if is_jpeg:
                result = copy_file(src, dst)
            else:
                result = convert_one(src, dst, quality)

            if result["skipped"]:
                skip_count += 1
                progress.advance(task_id)
                continue

            if result["ok"]:
                if is_jpeg:
                    copy_count += 1
                else:
                    ok_count += 1
                    delta = result["size_before"] - result["size_after"]
                    if delta > 0:
                        total_saved += delta

                if args.delete_originals:
                    if delete_original(src):
                        deleted_count += 1
            else:
                fail_count += 1
                errors.append((src.name, result["error"] or "неизвестная ошибка"))

            progress.advance(task_id)

    elapsed = time.monotonic() - start_time

    # ── Итоги ─────────────────────────────────────────────────────
    console.print()
    console.print(build_summary_table(
        ok=ok_count, copy=copy_count, skip=skip_count, fail=fail_count,
        total_saved=total_saved, deleted=deleted_count,
        elapsed=elapsed, file_count=len(files), errors=errors,
    ))
    console.print()


if __name__ == "__main__":
    main()
