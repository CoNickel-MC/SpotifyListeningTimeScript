import threading
import time
from time import time_ns

from fastapi import FastAPI, HTTPException
import requests
from pymongo import MongoClient
from pydantic import BaseModel
import os
from dotenv import load_dotenv




load_dotenv()


connection_string = os.getenv("MONGODB_CONNECTION_STRING")
client = MongoClient(connection_string)
db = client["Users"]
collection = db["Users"]

app = FastAPI()


class User(BaseModel):
	Name: str
	emailId: str
	currentAccessToken: str
	refreshToken: str
	listenTime: int
	lastCheckTime: int


@app.get("/")
async def read_root():
	return {"message": "Welcome to the TuneStats API!"}

@app.head("/")
async def read_root():
	return {"message": "Welcome to the TuneStats API!"}


@app.post("/addUser")
async def addUser(newUser:User):
	try:
		if collection.find_one({"emailId": newUser.emailId}):
			return
		newUser.lastCheckTime = time_ns()
		newUser.listenTime = 0
		collection.insert_one(newUser.model_dump())
	except Exception as e:
		raise HTTPException(status_code=500, detail="An error occurred.")


def refresh_access_token(user: User):
	url = 'https://accounts.spotify.com/api/token'
	payload = {
		'grant_type': 'refresh_token',
		'refresh_token': user.refreshToken,
		'client_id': os.getenv("SPOTIFY_CLIENT_ID"),
		'client_secret': os.getenv("SPOTIFY_CLIENT_SECRET")
	}

	response = requests.post(url, data=payload)
	if response.status_code == 200:
		new_token_info = response.json()
		new_access_token = new_token_info.get('access_token')
		collection.update_one({"emailId": user.emailId}, {"$set": {"currentAccessToken": new_access_token}})

def	checkListenTime():
	url = 'https://api.spotify.com/v1/me/player/currently-playing'

	while True:
		allUsers: list[User] = list(collection.find())
		for user in allUsers:
			headers = {
				'Authorization': f'Bearer {user.currentAccessToken}'
			}

			response = requests.get(url, headers=headers)

			if response.status_code == 401:
				refresh_access_token(user)
				headers['Authorization'] = f'Bearer {user.currentAccessToken}'
				response = requests.get(url, headers=headers)

			if response.status_code == 200:
				data = response.json()
				isPlaying = data.get('is_playing', None)

				if isPlaying is True:
					updatedUser = user.model_dump()
					updatedUser['listenTime'] += time_ns() - updatedUser['lastCheckTime']
					updatedUser['lastCheckTime'] = time_ns()
					collection.replace_one({"emailId": user.emailId}, updatedUser)

		time.sleep(45)


threading.Thread(target=checkListenTime, daemon=True).start()