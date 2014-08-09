import unittest
from bot import extract_youtube_id, MENTION_REGEX

class TestMentionRegex(unittest.TestCase):
    def test_positive(self):
        text = "redditliveleakbot +repost"
        self.assertIsNotNone(MENTION_REGEX.search(text))

    def test_negative(self):
        text = "/u/redditliveleakbot"
        self.assertIsNone(MENTION_REGEX.search(text))

        text = "redditliveleakbot"
        self.assertIsNone(MENTION_REGEX.search(text))

        text = "redditliveleakbot repost"
        self.assertIsNone(MENTION_REGEX.search(text))

class TestExtractYouTubeId(unittest.TestCase):
    def test_positive(self):
        url = "https://www.youtube.com/watch?v=IU5NSSzYygk"
        self.assertEquals(extract_youtube_id(url), "IU5NSSzYygk")

    def test_querystring(self):
        url = "https://www.youtube.com/watch?v=V5E8kDo2n6g&amp;feature=youtu.be"
        self.assertEquals(extract_youtube_id(url), "V5E8kDo2n6g")

    def test_long(self):
        url = "http://www.youtube.com/watch?feature=player_embedded&amp;v=LEN5rn47gYQ"
        self.assertEquals(extract_youtube_id(url), "LEN5rn47gYQ")

    def test_underscore(self):
        url = "https://www.youtube.com/watch?v=-8_0eAME3Xw"
        self.assertEquals(extract_youtube_id(url), "-8_0eAME3Xw")

    def test_hyphen(self):
        url = "http://www.youtube.com/watch?v=N-gPAMeXlQk"
        self.assertEquals(extract_youtube_id(url), "N-gPAMeXlQk")

    def test_short(self):
        url = "http://youtu.be/co9IZOSssFw"
        self.assertEquals(extract_youtube_id(url), "co9IZOSssFw")

    def test_short2(self):
        url = "http://youtu.be/Cy0RPWK_5wg"
        self.assertEquals(extract_youtube_id(url), "Cy0RPWK_5wg")

    def test_negative(self):
        url = "http://i.imgur.com/KJ0h3nZ.png"
        self.assertEquals(extract_youtube_id(url), None)

        url = "https://twitter.com/Praporec/status/489524665723809792/photo/1"
        self.assertEquals(extract_youtube_id(url), None)

from video_exists import video_exists
class TestVideoExists(unittest.TestCase):
    def setUp(self):
        import yaml
        import os.path as P
        with open(P.join(P.dirname(P.abspath(__file__)), "config.yml")) as fin:
            self.key = yaml.load(fin)["google_developer_key"]

    def test_positive(self):
        video_id = "jNQXAC9IVRw"
        self.assertTrue(video_exists(self.key, video_id))

    def test_negative(self):
        video_id = "Y7UmFIpenjs"
        self.assertFalse(video_exists(self.key, video_id))
