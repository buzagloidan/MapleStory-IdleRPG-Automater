# MapleStory Idle Bot

A Python automation bot for MapleStory Idle running on BlueStacks. Automates party quests by reading the screen and simulating inputs through ADB.

This bot does not modify the game. It only reads pixels and sends touch inputs.

## Disclaimer

This project is for **educational purposes only**. It is free to use, modify, and distribute. The authors assume no responsibility for any consequences resulting from the use of this software. Use at your own risk.

## Features

- Auto Party Quest with queue timeout handling
- Quest selection (Sleepywood, Ludibrium, Zakum, Orbis)
- Auto recovery from stuck states and connection loss
- Random jump actions during PQ
- GUI and CLI modes
- Configurable log retention (keep only the N most recent log files)

## Requirements

### BlueStacks Setup

1. Resolution: 960 x 540
2. Pixel Density: 240 DPI
3. ADB Enabled: Settings > Advanced > Android Debug Bridge
4. Restart BlueStacks after enabling ADB

### Python Dependencies

```bash
pip install -r requirements.txt
```

## Quick Start

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create templates (first time only):
```bash
python tools/template_creator.py --port 5555
```

3. Run the bot:
```bash
# GUI mode
python main.py

# CLI mode
python main.py --cli --port 5555 --quest sleepywood   # or ludibrium, zakum, orbis
```

## Project Structure

```
maple_bot/
├── main.py                 # Entry point
├── config.py               # Configuration management
├── core/                   # ADB, screen capture, template matching, input, logger
├── games/                  # Game-specific bot logic
├── gui/                    # GUI launcher
├── tools/                  # Template creator utility
├── templates/              # Template images for matching (e.g. sleepywood_wave_*, orbis_wave_*)
├── config/                 # Settings files
├── logs/                   # Timestamped log files (bot_YYYYMMDD_HHMMSS.log)
└── docs/                   # Documentation
```

## Configuration

Copy the example config and edit:
```bash
cp config/settings.yaml.example config/settings.yaml
```

Edit `config/settings.yaml`:

```yaml
loglevel: info
max-log-files: 5   # Keep only this many recent log files (0 = keep all)

adb:
  host: "127.0.0.1"
  port: 5555

bot-option:
  queue-timeout: 30
  quest-choice: sleepywood   # sleepywood | ludibrium | zakum | orbis
  random-jump: true
```

Logs are written to `logs/bot_YYYYMMDD_HHMMSS.log`. Only the most recent `max-log-files` logs are kept (default 5).

## CLI Options

```
--cli           Run in command-line mode
--port, -p      ADB port (default: 5555)
--quest, -q     Quest type: sleepywood, ludibrium, orbis
--debug, -d     Enable debug logging
--create-config Create default configuration file
```

## License

MIT License
