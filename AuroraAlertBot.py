# Aurora Alert Telegram Bot
# Copyright (C) 2026 Sandro Karhula
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException

from datetime import datetime
import sched, time
import time, traceback
import threading

stationShortNames = ['KEV','MAS','KIL','IVA','MUO','PEL','RAN','OUJ','MEK','HAN','NUR', 'TAR']
stationLongNames = ['kevo', 'masi', 'kilpisjarvi', 'ivalo', 'muonio', 'pello', 'ranua', 'oulujarvi', 'mekrijarvi', 'hankasalmi', 'nurmijarvi', 'tartu']
stationShortNameToLongName = dict(zip(stationShortNames, stationLongNames))
stationLongNameToShortName = dict(zip(stationLongNames, stationShortNames))

auroraData = {} # Data is updated every 5 minutes
lastUpdate = datetime.now()

def runWebScraper():
    print("Scraping aurora data...")

    global lastUpdate
    lastUpdate = datetime.now()

    options = webdriver.ChromeOptions()
    options.add_argument('--headless')

    driver = webdriver.Chrome(options=options)

    driver.get("https://space.fmi.fi/MIRACLE/RWC/r-index/en/")

    PATH = """/html/body/main[@role='main']/div[@class='flexims']/figure[1]/div[@class='imgbox map js-plotly-plot']
                /div[@class='plot-container plotly']/div[@class='user-select-none svg-container']
                /*[name()='svg' and @class='main-svg'][1]
                /*[name()='g' and @class='geolayer']
                /*[name()='g' and @class='geo geo']
                /*[name()='g' and @class='layer frontplot']
                /*[name()='g' and @class='scatterlayer']
                /*[name()='g' and @class='trace scattergeo']"""

    errors = [NoSuchElementException, ElementNotInteractableException]
    wait = WebDriverWait(driver, timeout=3, poll_frequency=.1, ignored_exceptions=errors)
    #wait.until(lambda d : len(driver.find_elements(By.XPATH, PATH)) >= 25)
    wait.until(lambda d : len(driver.find_elements(By.XPATH, PATH + f"[20]/*[name()='path' and @class='point']")) >= 1)

    elementCount = len(driver.find_elements(By.XPATH, PATH))
    print("element count:",elementCount)

    stationToIndex = {'KEV' : 0,'MAS' : 1,'KIL' : 2,'IVA' : 3,'MUO' : 4,'PEL' : 5,'RAN' : 6,'OUJ' : 7,'MEK' : 8,'HAN' : 9,'NUR' : 10,'TAR' : 11}
    indexToStation = {0 : 'KEV',1 : 'MAS',2 : 'KIL',3 : 'IVA',4 : 'MUO',5 : 'PEL',6 : 'RAN',7 : 'OUJ',8 : 'MEK',9 : 'HAN',10 : 'NUR',11 : 'TAR'}
    stations = []
    for i in range(elementCount):
        if driver.find_elements(By.XPATH, PATH + f"[{i}]/*[name()='path' and @class='point']"):
            element = driver.find_element(By.XPATH, PATH + f"[{i}]/*[name()='path' and @class='point']")
            style = element.get_attribute('style')
            if style[:11] == 'opacity: 1;':
                rgbSplits = style[(style.find('rgb')+4):].split(',') #e.g., ...rgb(102, 204, 238);...
                r = int(rgbSplits[0])
                g = int(rgbSplits[1])
                b = int(rgbSplits[2].partition(')')[0])
                hasData = (r != 0 or g != 0 or b != 0)

                transform = element.get_attribute('transform') #e.g., "translate(459.0974416142563,62.16295325387682)" -> "62.16295325387682"
                latitude = float(transform[10:-1].split(',')[1])
                
                stations.append((latitude, i, hasData, element))

    stations.sort()
    del stations[::2]

    print("station count:",len(stations))
    assert(len(stations) == 12)

    PATH_DATA = """/html/body/main[@role='main']/div[@class='flexims']/figure[1]/div[@class='imgbox map js-plotly-plot']
                    /div[@class='plot-container plotly']/div[@class='user-select-none svg-container']
                    /*[name()='svg' and @class='main-svg'][3]
                    /*[name()='g' and @class='hoverlayer']
                    /*[name()='g' and @class='hovertext']
                    /*[name()='text' and @class='nums']"""

    activityDict = {'No d' : 'No Data', 'No a': 'No Activity', 'Medi' : 'Medium Activity', 'High' : 'High Activity'} # No D = No Data, No A = No activity, Medi = Medium activity, High = High activity

    def getStationData(station):
        stationIndex = stationToIndex[station]
        for i in range(len(stations)):
            if stations[stationIndex][2]:
                break
            else:
                stationIndex = (stationIndex) % len(stations)

        action = ActionChains(driver)
        action.move_to_element(stations[stationIndex][3])
        action.perform()

        wait.until(lambda d : driver.find_element(By.XPATH, PATH_DATA).get_attribute("data-unformatted"))

        data = driver.find_element(By.XPATH, PATH_DATA).get_attribute("data-unformatted") # <b>Nurmijärvi (NUR)</b><br><br>Auroral activity: No activity<br>R: 6

        place = data[data.find(')</b>')-3:data.find(')</b>')] # 3 letter station identifier
        auroralActivity = activityDict[data[data.find('activity: ')+10:data.find('activity: ')+14]]
        Rstring = data[data.find('<br>R: ')+7:].strip()
        if Rstring.isnumeric():
            R = int(Rstring)
        else:
            previousStation = place
            R = None
            while R == None and previousStation != 'KEV':
                previousStation = indexToStation[(stationToIndex[place] + 11) % 12] # Select higher latitude data
                (auroralActivity, R) = auroraData[previousStation]
            
            if R == None:
                previousStation = place
                while R == None and previousStation != 'TAR':
                    previousStation = indexToStation[(stationToIndex[place] + 13) % 12] # Select lower latitude data
                    (auroralActivity, R) = auroraData[previousStation]

            if R == None:
                print("Warning: No data is available! Either all stations are offline or something is wrong.")

        return (place, auroralActivity, R)

    for station in stationShortNames:
        (place, auroralActivity, R) = getStationData(station)
        auroraData[place] = (auroralActivity, R)
        
        print(f"Place: {place}, Activity: {auroralActivity}, R-value: {R}")


from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackContext
from typing import Final

import orjson

# Edit the below to host the bot
TOKEN: Final = ''
BOT_USERNAME: Final = ''

HELP_TEXT = """
This bot provides notifications for auroras in Finland and Estonia. It scrapes geomagnetic data from https://rwc-finland.fmi.fi/index.php/auroral-activity/ every 5 minutes. The bot can also provide cloud coverage, horizontal visibility, sunrise, and sunset information near Espoo, Finland. The weather data originates from 3 observation stations in Tapiola, Nuuksio, and Kaisaniemi. It is scraped from https://en.ilmatieteenlaitos.fi/weather/espoo.

You can use the following commands to control me:

/help - to display this information again

/subscribe location <activity level> - to subscribe to aurora notifications for a given location and geomagnetic activity level
e.g., '/subscribe nurmijarvi medium'
Valid locations (ascending lattitude):
- Kevo
- Masi
- Kilpisjarvi
- Ivalo
- Muonio
- Pello
- Ranua
- Oulujarvi
- Mekrijarvi
- Hankasalmi
- Nurmijarvi
- Tartu
Valid activity levels include:
- Medium (recommended for southern regions and for viewing weak auroras)
- High

/unsubscribe <location> - unsubscribes from aurora notifications for a given location. If location is left empty, unsubscribes from all locations

/updateinterval <time> - to set how often you want to be notified about auroras, default is 5 min. <time> must be a multiple of 5, with 5 being the minimum. You'll receive the first notification as soon as auroras may appear, but every subsequent notification will be limited by the interval time.

/geomagneticdata - prints geomagnetic data for all stations in Finland and Estonia. This data is scraped from https://rwc-finland.fmi.fi/index.php/auroral-activity/.

/weatherdata - [currently unimplemented] prints relevant weather data near Espoo, Finland."""

from collections import defaultdict
userSubscriptions = defaultdict(dict)
userIntervals = {}

import os

fileUserSubscriptions = os.path.dirname(os.path.abspath(__file__)) + '\\userSubscriptions.json'
fileUserIntervals = os.path.dirname(os.path.abspath(__file__)) + '\\userIntervals.json'

import json

def saveUserSubscriptions():
    print("Trying to save user subscriptions...")
    with open(fileUserSubscriptions, 'w') as f: 
        json.dump(userSubscriptions, f)
        print("saving file to:", fileUserSubscriptions)


def loadUserPreferences():
    with open(fileUserIntervals, 'r') as f:
        userIntervals.clear()
        userIntervals.update(json.load(f))

    with open(fileUserSubscriptions, 'r') as f:
        userSubscriptions.clear()
        userSubscriptions.update(json.load(f))
        for user in userSubscriptions.keys():
            job_queue.run_repeating(callback=notificationCallback, interval=60*userIntervals.get(user, 5), first=0, chat_id=int(user), name=user)


def saveUserIntervals():
    with open(fileUserIntervals, 'w') as f: 
        json.dump(userIntervals, f)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, disable_web_page_preview=True)
    print(f"""User {context._chat_id} requested the start text.""")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, disable_web_page_preview=True)
    print(f"""User {context._chat_id} requested the help text.""")


async def notificationCallback(context: ContextTypes.DEFAULT_TYPE):
    print("Running notification callback...")
    high = []
    medium = []
    for station in stationLongNames:
        if station in userSubscriptions[str(context._chat_id)] and (auroraData[stationLongNameToShortName[station]][0] == 'High Activity' or (auroraData[stationLongNameToShortName[station]][0] == 'Medium Activity' and userSubscriptions[str(context._chat_id)][station] == 'medium')):
            (activity, R) = auroraData[stationLongNameToShortName[station]]
            if activity == 'Medium Activity':
                medium.append((station, R))
            else: 
                high.append((station, R))
            foundData = True
    
    if high or medium:
        notification = "Aurora Alert!"
        if high:
            notification += " High activity reached in " + ', '.join([f"{i[0]} (R={i[1]})" for i in high]) + "."
        if medium:
            notification += " Medium activity reached in " + ', '.join([f"{i[0]} (R={i[1]})" for i in medium]) + "."
        
        await context.bot.send_message(chat_id=context.job.chat_id, text=notification)
        print(f"""User {context._chat_id} has received the notification: {notification}""")


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    (_, location, probability) = update.message.text.split()
    locationLower = location.lower()
    probabilityLower = probability.lower()
    if locationLower in stationLongNames and probabilityLower in ['medium', 'high']:
        if str(context._chat_id) not in userSubscriptions:
            context.job_queue.run_repeating(callback=notificationCallback, interval=60*userIntervals.get(str(context._chat_id), 5), first=0, chat_id=context._chat_id, name=str(update.effective_chat.id))
        
        userSubscriptions[str(context._chat_id)][locationLower] = probabilityLower
        saveUserSubscriptions()
        await update.message.reply_text(f"""You have subscribed to be notified when auroras in {locationLower.capitalize()} have a {probabilityLower.capitalize()} activity level! You will be notified of auroras every {userIntervals.get(str(context._chat_id), 5)} minutes while the probability is high enough.""")
        print(f"""User {context._chat_id} has subscribed to be notified when auroras in {locationLower.capitalize()} have a {probabilityLower.capitalize()} activity level! They will be notified of auroras every {userIntervals.get(str(context._chat_id), 5)} minutes while the probability is high enough.""")
    else:
        if locationLower not in stationLongNames and probabilityLower not in ['medium', 'high']:
            await update.message.reply_text(f"""Invalid location '{location}'. Run /help to see a list of valid locations. Invalid activity level '{probability}'. Only 'Medium' and 'High' are valid.""")
            print(f"""User {context._chat_id} inputted invalid location '{location}'. Run /help to see a list of valid locations. Invalid activity level '{probability}'. Only 'Medium' and 'High' are valid.""")
        elif locationLower not in stationLongNames:
            await update.message.reply_text(f"""Invalid location '{location}'. Run /help to see a list of valid locations.""")
            print(f"""User {context._chat_id} inputted invalid location '{location}'. Run /help to see a list of valid locations.""")
        else:
            await update.message.reply_text(f"""Invalid activity level '{probability}'. Only 'Medium' and 'High' are valid.""")
            print(f"""User {context._chat_id} inputted invalid activity level '{probability}'. Only 'Medium' and 'High' are valid.""")


async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    input = update.message.text.split()
    if len(input) == 2:
        (command, location) = input
        locationLower = location.lower()
        if locationLower not in stationLongNames:
            await update.message.reply_text(f"""Invalid location '{location}'. Run /help to see a list of valid locations.""")
            print(f"""User {context._chat_id} inputed invalid location '{location}'. Run /help to see a list of valid locations.""")
        elif locationLower not in userSubscriptions[str(context._chat_id)]:
            await update.message.reply_text(f"""You aren't subscriped to '{location}'.""")
            print(f"""User {context._chat_id} tried to unsubscribe from '{location}', but they weren't subscribed.""")
        else:
            userSubscriptions[str(context._chat_id)].pop(locationLower, None)
            saveUserSubscriptions()
            await update.message.reply_text(f"""Unsubscribed from '{location}'""")
            print(f"""User {context._chat_id} unsubscribed from '{location}'""")
    else:
        userSubscriptions[str(context._chat_id)].clear()
        saveUserSubscriptions()
        await update.message.reply_text(f"""Unsubscribed from all locations""")
        print(f"""User {context._chat_id} unsubscribed from all locations""")

    if userSubscriptions[str(context._chat_id)] == {}:
        jobs = context.job_queue.get_jobs_by_name(str(update.effective_chat.id))
        for job in jobs:
            job.schedule_removal()


async def geomagneticdata_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    updateTime = "{:d}-{:d}-{:d} {:02d}:{:02d}".format(lastUpdate.year, lastUpdate.month, lastUpdate.day, lastUpdate.hour, lastUpdate.minute)
    dataMessage = f"Geomagnetic data for all stations (last scraped at {updateTime}):"
    for station in stationShortNames:
        (activity, R) = auroraData[station]
        dataMessage += f"""\nActivity in {stationShortNameToLongName[station].capitalize()}: {activity}, R-index: {R}"""

    dataMessage += f"""\n\nMedium activity corresponds to a 50% probability of weak auroras, while high activity corresponds to a 50% probability of strong auroras. The data has been scraped from https://rwc-finland.fmi.fi/index.php/auroral-activity/."""
    await update.message.reply_text(dataMessage)
    print(f"""User {context._chat_id} requested geomagnetic data.""")


async def weatherdata_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""Weather data scraping is currently unimplemented!""")
    print(f"""User {context._chat_id} requested weather data but it is currently unimplemented.""")


async def updateinterval_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    (command, interval) = update.message.text.split()
    if interval.isnumeric() and int(interval) % 5 == 0 and int(interval) >= 5:
        if int(interval) == userIntervals[str(context._chat_id)]:
            await update.message.reply_text(f"""Update interval is already set to {interval}""")
            print(f"""User {context._chat_id} tried to change update interval to {interval}, but it was already set to this value.""")
        else:
            userIntervals[str(context._chat_id)] = int(interval)
            saveUserIntervals()
            await update.message.reply_text(f"""Changed update interval to {interval}""")
            print(f"""Changed user {context._chat_id} update interval to {interval}""")
    else:
        await update.message.reply_text(f"""Invalid interval value '{interval}'. Interval must be divisible by 5 and >= 5.""")
        print(f"""User {context._chat_id} inputed an invalid interval value '{interval}'. Interval must be divisible by 5 and >= 5.""")

    jobs = context.job_queue.get_jobs_by_name(str(update.effective_chat.id))
    for job in jobs:
        job.schedule_removal()

    context.job_queue.run_repeating(callback=notificationCallback, interval=60*userIntervals.get(str(context._chat_id), 5), first=0, chat_id=context._chat_id, name=str(update.effective_chat.id))


def handle_response(text: str) -> str:
    text = text.lower()
    return f"Unknown command. Type /help to view available commands."


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    messageType = update.message.chat.type
    text = update.message.text

    print(f'User ({update.message.chat.id}) in {messageType}: "{text}"')

    if messageType == 'group':
        if BOT_USERNAME in text:
            newText = text.replace(BOT_USERNAME, '').strip()
            response = handle_response(newText)
        else:
            return
    else:
        response = handle_response(text)

    print('Bot: ', response)
    await update.message.reply_text(response)


async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f'Update "{update}" caused error "{context.error}"')


def autoUpdateAuroraData(delay, task):
  next_time = time.time() + delay
  while True:
    time.sleep(max(0, next_time - time.time()))
    try:
      task()
    except Exception:
      traceback.print_exc()

    next_time += (time.time() - next_time) // delay * delay + delay


if __name__ == '__main__':
    print('Starting bot...')
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('geomagneticdata', geomagneticdata_command))
    app.add_handler(CommandHandler('weatherdata', weatherdata_command))

    app.add_handler(MessageHandler(filters.Regex(r'^(\/subscribe\s+(\w+)\s+(\w+)\s*)$'), subscribe_command))
    app.add_handler(MessageHandler(filters.Regex(r'^(\/unsubscribe(\s+(\w*))?\s*)$'), unsubscribe_command))
    app.add_handler(MessageHandler(filters.Regex(r'^(\/updateinterval\s+(\w+)\s*)$'), updateinterval_command))
    
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    app.add_error_handler(error)

    job_queue = app.job_queue
    
    runWebScraper()
    threading.Thread(target=lambda: autoUpdateAuroraData(300, runWebScraper)).start()

    print('Loading user preferences...')
    loadUserPreferences()

    print('Polling...')

    app.run_polling(poll_interval=3)
