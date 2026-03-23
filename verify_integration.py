import requests
import json

url = "http://localhost:8081/news/personalize"
data = {
    "current_persona": "student",
    "query": "artificial intelligence",
    "click_history": [1, 1, 0],
    "user_id": "test_user_123"
}

try:
    print(f"Testing endpoint: {url}")
    response = requests.post(url, json=data)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print("Success! Response summary:")
        print(f"  Applied Persona: {result.get('persona_applied')}")
        print(f"  Top Persona: {result.get('top_persona')}")
        print(f"  Articles count: {len(result.get('top_articles', []))}")
        for idx, art in enumerate(result.get('top_articles', [])):
            print(f"    {idx+1}. {art.get('original_title')[:50]}...")
    else:
        print(f"Error Response: {response.text}")
except Exception as e:
    print(f"Error during test: {e}")
