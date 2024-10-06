import threading
import time
from time import time_ns

from fastapi import FastAPI, HTTPException
import requests
from pymongo import MongoClient
from pydantic import BaseModel



connection_string = "mongodb+srv://springterror228:root@users.ye13s.mongodb.net/?retryWrites=true&w=majority&appName=Users"
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


def	checkListenTime():
	url = 'https://api.spotify.com/v1/me/player/currently-playing'

	while True:
		allUsers: list[User] = list(collection.find())
		for user in allUsers:
			updatedUser = user.model_copy()
			headers = {
				'Authorization': f'Bearer {user.currentAccessToken}'
			}

			response = requests.get(url, headers=headers)

			if response.status_code == 200:
				data = response.json()
				isPlaying = data.get('is_playing', None)
				updatedUser.listenTime += time_ns() - updatedUser.lastCheckTime
				updatedUser.lastCheckTime = time_ns()

				if isPlaying is True:
					collection.replace_one({"emailId": user.emailId}, updatedUser.model_dump())
		time.sleep(45)



threading.Thread(target=checkListenTime, daemon=True).start()