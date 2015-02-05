import re
import requests
import json
import logging
import os.path as P
import subprocess as sub

logger = logging.getLogger(__name__)


def extract_id(url):
    """Extract a YouTube ID from a URL."""
    #
    # YouTube attribution links.
    # More info:
    # http://techcrunch.com/2011/06/01/youtube-now-lets-you-license-videos-under-creative-commons-remixers-rejoice/
    # Example:
    # http://www.youtube.com/attribution_link?a=P3m5pZfhr5Y&u=%2Fwatch%3Fv%3DHnc-1rXLx_4%26feature%3Dshare
    m = re.search("watch%3Fv%3D(?P<id>[a-zA-Z0-9-_]{11})", url)
    if m:
        return m.group("id")

    #
    # Regular YouTube links.
    #
    m = re.search(r"youtu\.?be.*(v=|/)(?P<id>[a-zA-Z0-9-_]{11})", url)
    if m:
        return m.group("id")
    return None


def video_exists(youtube_id, user_agent, developer_key):
    """Return True if the video is still accessible on YouTube."""
    meth_name = "youtube_video_exists"
    url = "https://www.googleapis.com/youtube/v3/videos"
    headers = {"User-Agent": user_agent}
    params = {"key": developer_key, "part": "id", "id": youtube_id}
    r = requests.get(url, params=params, headers=headers)
    logger.debug("%s: youtube_id: %s status_code: %d",
                 meth_name, repr(youtube_id), r.status_code)
    if r.status_code != 200:
        logger.error("%s: unexpected status_code: %d",
                     meth_name, r.status_code)
        logger.error("%s: GET response: %s", meth_name, repr(r.text))
        raise YoutubeException("bad HTTP response (%d)" % r.status_code)
    obj = json.loads(r.text)
    return obj["pageInfo"]["totalResults"] > 0


def download(dest_dir, youtube_id):
    meth_name = "download"
    template = P.join(dest_dir, "%(id)s.%(ext)s")
    args = ["youtube-dl", "--verbose", "--output", template, "--", youtube_id]
    logger.debug("%s: %s", meth_name, " ".join(args))
    process = sub.Popen(args, stdin=sub.PIPE, stdout=sub.PIPE,
                        stderr=sub.STDOUT)
    stdout, _ = process.communicate()
    logger.debug("%s: return_code: %d", meth_name, process.returncode)
    if process.returncode != 0:
        logger.error("%s: youtube-dl stdout/stderr follows\n%s", meth_name,
                     stdout)
        logger.error("%s: youtube-dl exited with an error (%d)",
                     meth_name, process.returncode)


class YoutubeException(Exception):
    pass
