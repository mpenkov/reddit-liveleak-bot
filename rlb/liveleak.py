"""Upload a video to liveleak."""

import requests
import re
import os.path as P
import time
import xml.etree.ElementTree as ET
import urllib
import json
import logging

logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)

from StringIO import StringIO
from lxml import etree
from requests_toolbelt import MultipartEncoder

CATEGORIES = {
    "World News": 2, "Ukraine": 37, "Regional News": 3, "Other News": 4,
    "Politics": 5, "Syria": 33, "Afghanistan": 8, "Iraq": 7, "Iran": 9,
    "Other Middle East": 10, "WTF": 13, "Creative": 14,
    "Other Entertainment": 16, "Music": 20, "Liveleak Challenges": 21,
    "Weapons": 22, "Sports": 29, "Yawn": 34, "Vehicles": 36, "LiveLeaks": 17,
    "Citizen Journalism": 19, "Your Say": 11, "Hobbies": 35,
    "Other Items from Liveleakers": 24, "Religion": 26, "Conspiracy": 27,
    "Propaganda": 28, "Science and Technology": 30, "Nature": 31,
    "History": 32, "Other": 18
}


class LiveLeakException(Exception):
    pass


class Uploader(object):
    def __init__(self, user_agent):
        self.cookies = None
        self.user_agent = user_agent

    def login(self, username, password):
        meth_name = "login"
        data = {"user_name": username, "user_password": password, "login": 1}
        r = requests.post(
            "http://www.liveleak.com/index.php",
            data=data, headers={"User-Agent": self.user_agent})
        if r.status_code != 200:
            raise LiveLeakException("bad HTTP response (%d)" % r.status_code)

        keys = ["PHPSESSID", "liveleak_safe_mode", "liveleak_use_old_player",
                "liveleak_user_password", "liveleak_user_token", "user-agent"]

        self.cookies = {}
        for key in keys:
            self.cookies[key] = r.cookies[key]

        logger.debug("%s: cookies: %s", meth_name, self.cookies)

    def upload(self, path):
        meth_name = "upload"
        r = requests.get(
            "http://www.liveleak.com/item?a=add_item",
            cookies=self.cookies, headers={"User-Agent": self.user_agent})
        logger.debug(
            "%s: add_item GET status_code: %d", meth_name, r.status_code)
        if r.status_code != 200:
            raise LiveLeakException("bad HTTP response (%d)" % r.status_code)

        multipart_params = extract_multipart_params(r.text)
        logger.debug(
            "%s: multipart_params: %s", meth_name, repr(multipart_params))
        if multipart_params is None:
            raise LiveLeakException("unable to parse upload form")

        connection = extract_connection(r.text)
        logger.debug("%s: connection: %s", meth_name, connection)

        connect_string = re.search("connect_string=(?P<connect_string>[^&]+)",
                                   r.text).group("connect_string")
        logger.debug("%s: connect_string: %s", meth_name, repr(connect_string))

        file_token = self.__aws_upload(path, multipart_params, connect_string)
        return file_token, connection

    def publish(self, title, body, tags, category, connection):
        meth_name = "publish"
        data = {
            "title": title,
            "body_text": body,
            "tag_string": tags,
            "category_array[]": CATEGORIES[category],
            "address": "",
            "location_id": 0,
            "is_private": 0,
            "disable_risky_commenters": 0,
            "content_rating": "MA",
            "occurrence_date_string": "",
            "enable_financial_support": 0,
            "financial_support_paypal_email": "",
            "financial_support_bitcoin_address": "",
            "agreed_to_tos": "on",
            "connection": connection
        }

        r = requests.post(
            "http://www.liveleak.com/item?a=add_item&ajax=1",
            data=data, cookies=self.cookies,
            headers={"User-Agent": self.user_agent})
        logger.debug(
            "%s: add_item POST status_code: %d", meth_name, r.status_code)
        logger.debug("%s: add_item POST response: %s", meth_name, repr(r.text))

        obj = json.loads(r.text)
        if obj["success"] != 1:
            raise Exception(obj["msg"])

        return obj["item_token"]

    def delete(self, file_token):
        meth_name = "delete"
        r = requests.get(
            "http://www.liveleak.com/file",
            params={"a": "delete_file", "file_token": file_token},
            cookies=self.cookies, headers={"User-Agent": self.user_agent})
        logger.debug("%s: GET status_code: %d", meth_name, r.status_code)
        # logger.debug("%s: GET response: %s", meth_name, repr(r.text))

    def __aws_upload(self, path, multipart_params, connect_string):
        """Upload a file to AWS.
        Raises Exception on failure.
        Returns a file_token in case of successs."""
        meth_name = "__aws_upload"
        #
        # Mangle the filename (add timestamp, remove special characters).
        # This is similar to what the JS in the add_item form does.
        # It isn't exactly the same, but it's good enough.
        #
        filename = P.basename(path)
        fixed_file_name_part, extension = P.splitext(filename)
        fixed_file_name_part = "".join(
            [ch for ch in fixed_file_name_part if ch.isalnum()])
        timestamp = time.time()
        #
        # Filename must be a raw Python string (not unicode)
        #
        filename = str(fixed_file_name_part + "_" + str(timestamp) + extension)
        multipart_params["name"] = filename
        multipart_params["key"] = multipart_params["key"].replace(
            "${filename}", filename)

        #
        # Fields must be in the right order.
        #
        fields = ["name", "key", "Filename", "acl", "Expires",
                  "Content-Type", "success_action_status", "AWSAccessKeyId",
                  "policy", "signature"]
        fields = [(name, multipart_params[name]) for name in fields]
        fields.append(("file", ("filename", open(path, "rb"), "video/mp4")))
        logger.debug("%s: fields: %s", meth_name, str(fields))

        #
        # http://toolbelt.readthedocs.org/en/latest/user.html#uploading-data
        #
        m = MultipartEncoder(fields=fields)

        headers = {
            "Origin": "http://www.liveleak.com",
            "Accept-Encoding": "gzip,deflate,sdch",
            "Host": "llbucs.s3.amazonaws.com",
            "Accept-Language": "en-US,en;q=0.8,ja;q=0.6,ru;q=0.4",
            "User-Agent": self.user_agent,
            "Content-Type": m.content_type,
            "Accept": "*/*",
            "Referer": "http://www.liveleak.com/item?a=add_item",
            "Connection": "keep-alive"
        }

        r = requests.post(
            "https://llbucs.s3.amazonaws.com/",
            cookies=self.cookies, headers=headers, data=m)
        logger.debug("%s: POST status_code: %d", meth_name, r.status_code)
        logger.debug("%s: add_item POST response: %s", meth_name, repr(r.text))

        assert r.status_code == 201, "couldn't upload to AWS"

        root = ET.fromstring(r.text)
        amazon_response = {}
        for key in ["Location", "Bucket", "Key", "ETag"]:
            amazon_response[key] = root.find(key).text

        logger.debug(
            "%s: amazon_response: %s", meth_name, repr(amazon_response))

        query_params = {
            "a": "add_file",
            "ajax": 1,
            "connect_string": connect_string,
            "s3_key": amazon_response["Key"],
            "fn": urllib.quote(filename),
            "resp": urllib.quote(r.text)
        }

        logger.debug("%s: query_params: %s", meth_name, repr(query_params))

        r = requests.get(
            "http://www.liveleak.com/file",
            params=query_params, cookies=self.cookies,
            headers={"User-Agent": self.user_agent})
        logger.debug("%s: GET status_code: %d", meth_name, r.status_code)
        logger.debug("%s: GET response: %s", meth_name, repr(r.text))

        try:
            obj = json.loads(r.text)
        except ValueError:
            raise LiveLeakException("unable to decode JSON from response")

        if obj["success"] != 1:
            raise LiveLeakException(obj["msg"])

        return obj["file_token"]


def extract_multipart_params(html):
    """Extract the multipart_params dict from the add_item.html.
    Returns a dictionary on success, None on failure."""
    meth_name = "extract_multipart_params"
    keys = ["key", "Filename", "acl", "Expires", "Content-Type",
            "success_action_status", "AWSAccessKeyId", "policy", "signature"]
    multipart_params = {}
    ptn = re.compile("'(?P<key>%s)' *: *'(?P<value>[^']+)'" % "|".join(keys))
    found_params = False
    for line in [l.strip() for l in html.split("\n")]:
        if found_params and line.startswith("},"):
            break
        elif found_params:
            match = ptn.search(line)
            if not match:
                continue
            multipart_params[match.group("key")] = match.group("value")
        elif line.startswith("multipart_params: {"):
            found_params = True
            continue
    for k in keys:
        if k not in multipart_params:
            logging.error("%s: missing key: %s", meth_name, repr(k))
            return None
    return multipart_params


def extract_connection(html):
    #
    # Get the connection number (the value of the hidden input below):
    #
    # <input id="connection" name="connection" value="772_1405579810"
    #  type="hidden"/>
    #
    root = etree.parse(StringIO(html), etree.HTMLParser())
    connection = root.xpath("//input[@id='connection']")
    return connection[0].get("value")
