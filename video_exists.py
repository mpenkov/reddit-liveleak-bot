"""Check if the video with a specific YouTube ID still exists."""
import requests
import json
import logging
from user_agent import USER_AGENT

logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)


def video_exists(developer_key, youtube_id):
    meth_name = "video_exists"
    url = "https://www.googleapis.com/youtube/v3/videos"
    headers = {"User-Agent": USER_AGENT}
    params = {"key": developer_key, "part": "id", "id": youtube_id}
    r = requests.get(url, params=params, headers=headers)
    logger.debug("%s: youtube_id: %s status_code: %d", meth_name, `youtube_id`, r.status_code)
    if r.status_code != 200:
        logger.error("%s: unexpected status_code: %d", meth_name, r.status_code)
        logger.error("%s: GET response: %s", meth_name, `r.text`)
    assert r.status_code == 200
    obj = json.loads(r.text)
    return obj["pageInfo"]["totalResults"] > 0


def main():
    import sys
    import yaml
    with open("config.yml") as fin:
        doc = yaml.load(fin)
    print video_exists(doc["google_developer_key"], sys.argv[1])

if __name__ == "__main__":
    main()
