"""Check if the video with a specific YouTube ID still exists."""
import requests
import json
from user_agent import USER_AGENT

def video_exists(developer_key, youtube_id):
    url = "https://www.googleapis.com/youtube/v3/videos"
    headers = {"User-Agent": USER_AGENT}
    params = {"key": developer_key, "part": "id", "id": youtube_id}
    r = requests.get(url, params=params)
    assert r.status_code == 200
    obj = json.loads(r.text)
    return obj["pageInfo"]["totalResults"] > 0

if __name__ == "__main__":
    import sys
    import yaml
    with open("config.yml") as fin:
        doc = yaml.load(fin)
    print exists(doc["google_developer_key"], sys.argv[1])
