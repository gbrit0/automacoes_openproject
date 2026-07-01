import requests

OPENPROJECT_API_KEY = '465d09a37aab01a3b3cf48490498829a51dfaf8745c5561da4dbd36d129131d0'

url = f"http://172.49.49.8:25011/api/v3/search?q=1161"

response = requests.get(url, auth=('apikey', OPENPROJECT_API_KEY))

response.raise_for_status()

print(response.json())