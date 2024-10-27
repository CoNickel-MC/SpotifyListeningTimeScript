import threading
import time
from time import time_ns

from fastapi import FastAPI, HTTPException
import requests
from pymongo import MongoClient
from pydantic import BaseModel
import os
from dotenv import load_dotenv
import logging


load_dotenv()


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


connectionString = os.getenv("MONGODB_CONNECTION_STRING")
client = MongoClient(connectionString)
db = client["Users"]
collection = db["Users"]


app = FastAPI()


class User(BaseModel):
    name: str
    emailId: str
    currentAccessToken: str
    refreshToken: str
    listenTime: int
    lastCheckTime: int

@app.get("/")
async def readRoot():
    return {"message": "Welcome to the TuneStats API!"}

@app.head("/")
async def readRootHead():
    return {"message": "Welcome to the TuneStats API!"}

@app.post("/addUser")
async def addUser(newUser: User):
    try:
        if collection.find_one({"emailId": newUser.emailId}):
            return {"message": "User already exists"}
        newUser.lastCheckTime = time_ns()
        newUser.listenTime = 0
        collection.insert_one(newUser.model_dump())
    except Exception as e:
        logger.error(f"Error adding user {newUser.emailId}: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while adding user.")


def refreshAccessToken(user: User):
    url = 'https://accounts.spotify.com/api/token'
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': user.refreshToken,
        'client_id': os.getenv("SPOTIFY_CLIENT_ID"),
        'client_secret': os.getenv("SPOTIFY_CLIENT_SECRET")
    }

    response = requests.post(url, data=payload)
    if response.status_code == 200:
        newTokenInfo = response.json()
        newAccessToken = newTokenInfo.get('access_token')
        newRefreshToken = newTokenInfo.get('refresh_token') or user.refreshToken

        collection.update_one(
            {"emailId": user.emailId},
            {"$set": {
                "currentAccessToken": newAccessToken,
                "refreshToken": newRefreshToken
            }}
        )

        logger.info(f"Access token refreshed for user: {user.emailId}")
    else:
        logger.error(f"Failed to refresh token for user: {user.emailId} with status code {response.status_code}")


def checkListenTime():
    url = 'https://api.spotify.com/v1/me/player/currently-playing'

    while True:
        allUsers = collection.find()
        for userFromCollection in allUsers:
            if userFromCollection.get('refreshToken') is None:
                logger.error(f"Skipping user {userFromCollection.get('emailId')} due to missing refreshToken.")
                continue

            try:
                user = User(**userFromCollection)

                headers = {
                    'Authorization': f'Bearer {user.currentAccessToken}'
                }

                response = requests.get(url, headers=headers)
                logger.info(f"User {user.emailId}: Spotify API response {response.status_code}")


                collection.update_one(
                    {"emailId": user.emailId},
                    {"$set": {"lastCheckTime": time_ns()}}
                )

                if response.status_code == 401:
                    logger.info(f"Token expired for user {user.emailId}, refreshing...")
                    refreshAccessToken(user)


                    refreshedUser = collection.find_one({"emailId": user.emailId})
                    if refreshedUser:
                        headers['Authorization'] = f"Bearer {refreshedUser['currentAccessToken']}"
                        logger.info(f"Access token refreshed for user: {user.emailId}")


                    response = requests.get(url, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    isPlaying = data.get('is_playing', None)

                    if isPlaying:
                        updatedUser = user.model_dump()
                        updatedUser['listenTime'] += time_ns() - updatedUser['lastCheckTime']
                        updatedUser['lastCheckTime'] = time_ns()
                        collection.replace_one({"emailId": user.emailId}, updatedUser)
                        logger.info(f"Updated listen time for user: {user.emailId}")
            except Exception as e:
                logger.error(f"Error processing user {userFromCollection.get('emailId')}: {e}")

        time.sleep(45)

threading.Thread(target=checkListenTime, daemon=True).start()
