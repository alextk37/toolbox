<div align="center">

```
 _______ ____   ____  _      ____   ______  __
|__   __/ __ \ / __ \| |    |  _ \ / __ \ \/ /
   | | | |  | | |  | | |    | |_) | |  | \  /
   | | | |  | | |  | | |    |  _ <| |  | |> <
   | | | |__| | |__| | |____| |_) | |__| / . \
   |_|  \____/ \____/|______|____/ \____/_/\_\
```

**Персональное монорепо с инструментами и конфигами**

[![Tools](https://img.shields.io/badge/tools-1-blue)](.)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python)](.)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

</div>

---

## Что это

Один репозиторий — много независимых инструментов. Каждая папка живёт своей жизнью: свой `README.md`, свои зависимости, своя версия. Никаких монорепо-фреймворков — просто папки и здравый смысл.

Зачем:
- Не плодить 20 репозиториев на один скрипт
- Хранить конфиги и утилиты в одном месте
- Легко делиться: человек забирает только нужную папку

---

## Инструменты

| Папка | Назначение | Форматы |
|---|---|---|
| [image-converter](image-converter/) | Конвертер изображений → JPEG (HEIC, PNG, WEBP, AVIF, …) с Rich-интерфейсом | `HEIC` `PNG` `WEBP` `AVIF` `TIFF` `BMP` `GIF` `SVG` `PSD` … |

---

## Как забрать только одну папку

Клонировать весь репозиторий ради одного скрипта — перебор. Вот три способа забрать отдельный инструмент.

### sparse-checkout — родной git, можно потом pull

```bash
git clone --filter=blob:none --sparse https://github.com/alextk37/toolbox.git
cd toolbox
git sparse-checkout set image-converter
```

Чтобы добавить ещё папку позже:

```bash
git sparse-checkout add другая-папка
```

### degit — одной командой, без git-истории

```bash
npx degit alextk37/toolbox/image-converter image-converter
```

`npx` скачает `degit` одноразово, ничего ставить не нужно.

### svn export — даже без git на машине

```bash
svn export https://github.com/alextk37/toolbox/trunk/image-converter
```

GitHub отдаёт любую папку через Subversion. Минус: нельзя обновить — только скачать заново.

---

## Что будет дальше

- `configs/` — dotfiles: `.zshrc`, настройки Neovim, tmux, Git
- `voice-relay/` — голосовой ретранслятор для iPhone → Telegram
- `scripts/` — одноразовые утилиты (бэкапы, cron-скрипты, парсеры)

Если хочешь что-то предложить — открывай Issue.

---

## Лицензия

MIT — делай что хочешь, просто сохрани копирайт.
