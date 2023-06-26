import os
import asyncio
import aiohttp
from pymongo import MongoClient
from datetime import datetime


# load env variables
if os.getenv("PIPENV_YES") == None:
  from dotenv import load_dotenv
  load_dotenv()


# summary for speed update task
NOT_LIVE_STORES = []
SCORES_UPDATED = 0

# get env variables
PAGE_SPEED_KEY = os.getenv("PAGE_SPEED_KEY")
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DBNAME=os.getenv("MONGO_DBNAME")

# get collection
def getColl(collName):
  client = MongoClient(MONGO_URI)
  db = client[MONGO_DBNAME]
  return db[collName]

# get premium stores from Mongo
def getPremiumStores():
  storesColl = getColl("stores")
  cursor = storesColl.find({
    "plan": {
      "$nin": ['free', "null"],
    },
    "app_version": "3",
  })
  stores = []

  for doc in cursor: # loop thourgh cursor
    stores.append(doc)

  print("Premium stores for speed updates: ", len(stores))
  return stores



# get status of each store
async def getLiveStores(storeList: dict):
  tasks = []
  for store in storeList:
    tasks.append(asyncio.ensure_future(checkSiteStatus(store)))
  statuses = await asyncio.gather(*tasks)
  liveStores = []
  for item in statuses:
    if (item["status"] == 200):
      liveStores.append({"storeUrl": item["storeUrl"], "storeId": item["storeId"]})
    else:
      NOT_LIVE_STORES.append(item["storeUrl"])

  print("Live stores for Score Updates: ", len(liveStores))
  return liveStores

# get site status
async def checkSiteStatus(store):
  url = store["store"]
  storeId = store["_id"]
  print("Checking status of: ", url)
  homeURL = f"https://{url}"
  async with aiohttp.ClientSession() as session:
    async with session.get(homeURL) as resp:
      return {"storeUrl": url, "status": resp.status, "storeId": storeId}

# get psi score
async def psi(storeObj):
  storeUrl = storeObj["storeUrl"]
  print("Checking speed score for ", storeUrl)
  # sample end point
  baseUrl = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
  query = f"?url=https://{storeUrl}&category=performance&strategy=desktop&key={PAGE_SPEED_KEY}"
  endpoint = baseUrl + query
  async with aiohttp.ClientSession() as session:
    try:
      async with session.get(endpoint) as resp:
        json = await resp.json()
        score = json["lighthouseResult"]["categories"]["performance"]["score"] * 100
        print({"storeUrl": storeUrl, "score": score})
        return {"storeUrl": storeUrl, "score": score, "storeId": storeObj["storeId"]}
    except  Exception as e:
      json = await resp.json()
      print("Error Response", json)
      print(e)

async def main():
  # get stores for score updates
  stores = getPremiumStores()

  # check live status
  liveStores = await getLiveStores(stores)

  print(liveStores)

  # check speed score for livestores
  tasks = []
  for item in liveStores:
    tasks.append(asyncio.ensure_future(psi(item)))
  # array of storeUrl/score
  psiResults = await asyncio.gather(*tasks)

  # update score values in DB
  speedScoreColl = getColl("speedscores")
  for item in psiResults:
    if (item == None):
      continue
    result = speedScoreColl.insert_one({
      "storeId": item["storeId"],
      "scores": {
        "home": {
          "desktop": item["score"]
        }
      },
      "requestedAt": datetime.now()
    })
    if result.inserted_id:
      print("SpeedScore updated for", item["storeUrl"])
      global SCORES_UPDATED
      SCORES_UPDATED = SCORES_UPDATED + 1


  # Task summary
  print("Scores Updated: ", SCORES_UPDATED)
  print("Stores not live", len(NOT_LIVE_STORES))
  print("URLs for not live stores", NOT_LIVE_STORES)

# asyncio.run(main())
