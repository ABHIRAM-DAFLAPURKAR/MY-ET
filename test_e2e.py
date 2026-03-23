import requests
import json

url = "http://localhost:8081/news/personalize"
data = {
    "article_text": "The stock market saw a significant rise today as investors gained confidence in the new economic policy.",
    "current_persona": "investor",
    "click_history": [1, 0, 1]
}

try:
    response = requests.post(url, json=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    print(f"Error: {e}")
