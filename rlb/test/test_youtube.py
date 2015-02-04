import unittest

import rlb.main
import rlb.youtube as youtube


class TestExtractYouTubeId(unittest.TestCase):

    def test_positive(self):
        url = "https://www.youtube.com/watch?v=IU5NSSzYygk"
        self.assertEquals(youtube.extract_id(url), "IU5NSSzYygk")

    def test_querystring(self):
        url = "https://www.youtube.com/watch?v=V5E8kDo2n6g&amp;\
feature=youtu.be"
        self.assertEquals(youtube.extract_id(url), "V5E8kDo2n6g")

    def test_long(self):
        url = "http://www.youtube.com/watch?feature=player_embedded&amp;\
v=LEN5rn47gYQ"
        self.assertEquals(youtube.extract_id(url), "LEN5rn47gYQ")

    def test_underscore(self):
        url = "https://www.youtube.com/watch?v=-8_0eAME3Xw"
        self.assertEquals(youtube.extract_id(url), "-8_0eAME3Xw")

    def test_hyphen(self):
        url = "http://www.youtube.com/watch?v=N-gPAMeXlQk"
        self.assertEquals(youtube.extract_id(url), "N-gPAMeXlQk")

    def test_short(self):
        url = "http://youtu.be/co9IZOSssFw"
        self.assertEquals(youtube.extract_id(url), "co9IZOSssFw")

    def test_short2(self):
        url = "http://youtu.be/Cy0RPWK_5wg"
        self.assertEquals(youtube.extract_id(url), "Cy0RPWK_5wg")

    def test_negative(self):
        url = "http://i.imgur.com/KJ0h3nZ.png"
        self.assertEquals(youtube.extract_id(url), None)

    def test_negative2(self):
        url = "https://twitter.com/Praporec/status/489524665723809792/photo/1"
        self.assertEquals(youtube.extract_id(url), None)

    def test_attribution(self):
        url = "http://www.youtube.com/attribution_link?\
a=P3m5pZfhr5Y&u=%2Fwatch%3Fv%3DHnc-1rXLx_4%26feature%3Dshare"
        self.assertEquals(youtube.extract_id(url), "Hnc-1rXLx_4")


class TestVideoExists(unittest.TestCase):

    def setUp(self):
        self.cfg = rlb.main.Config()

    def test_positive(self):
        video_id = "jNQXAC9IVRw"
        self.assertTrue(youtube.video_exists(video_id, self.cfg.user_agent,
                                             self.cfg.google_developer_key))

    def test_negative(self):
        video_id = "Y7UmFIpenjs"
        self.assertFalse(youtube.video_exists(video_id, self.cfg.user_agent,
                                              self.cfg.google_developer_key))
