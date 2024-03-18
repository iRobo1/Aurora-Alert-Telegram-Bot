# Aurora-Alert-Telegram-Bot
A telegram bot that notifies you about possible auroras in Finland and Estonia. It scrapes data from https://rwc-finland.fmi.fi/index.php/auroral-activity/ (there is no API available to obtain this data).

To run:
- set the `TOKEN` and `BOT_USERNAME` fields in `AuroraAlertBot.py`
- `pip install python-telegram-bot, selenium --upgrade`
- run `AuroraAlertBot.py` with python 3 (python 2 is untested)

I made this bot for fun, so don't expect it to be updated. The bot will break if the Finnish Meteorological Institute alters the website.
