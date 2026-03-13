from flask import Flask, request, jsonify
import jwt
import time
import os

app = Flask(__name__)

# These are set in the Cloud Provider's Dashboard, NOT in the code!
API_KEY = os.environ.get("BCFY_API_KEY")
API_KEY_ID = os.environ.get("BCFY_API_KEY_ID")
APP_ID = os.environ.get("BCFY_APP_ID")

@app.route('/get_token', methods=['POST'])
def get_token():
    data = request.json
    uid = data.get("uid")   # Optional: only sent for the second handshake
    utk = data.get("utk")   # Optional: only sent for the second handshake
    
    headers = {"alg": "HS256", "typ": "JWT", "kid": API_KEY_ID}
    current_time = int(time.time())
    
    # Base Payload
    payload = {
        "iss": APP_ID,
        "iat": current_time,
        "exp": current_time + 3600
    }

    # If the user provides their UID/Token, we upgrade the JWT to a "Master"
    if uid and utk:
        payload["sub"] = int(uid)
        payload["utk"] = utk

    signed_jwt = jwt.encode(payload, API_KEY, algorithm="HS256", headers=headers)
    return jsonify({"jwt": signed_jwt})

if __name__ == "__main__":
    app.run()
