import unittest
import os.path as P
import yaml
import mock
import datetime as dt

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from orm import Base, Video, State, Mention

from liveleak_upload import LiveLeakUploader
from bot import extract_youtube_id, MENTION_REGEX, locate_video, Bot
from liveleak_upload import extract_multipart_params
from video_exists import video_exists

CURRENT_DIR = P.dirname(P.abspath(__file__))


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
        url = "https://www.youtube.com/watch?v=V5E8kDo2n6g&amp;\
feature=youtu.be"
        self.assertEquals(extract_youtube_id(url), "V5E8kDo2n6g")

    def test_long(self):
        url = "http://www.youtube.com/watch?feature=player_embedded&amp;\
v=LEN5rn47gYQ"
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

    def test_negative2(self):
        url = "https://twitter.com/Praporec/status/489524665723809792/photo/1"
        self.assertEquals(extract_youtube_id(url), None)

    def test_attribution(self):
        url = "http://www.youtube.com/attribution_link?\
a=P3m5pZfhr5Y&u=%2Fwatch%3Fv%3DHnc-1rXLx_4%26feature%3Dshare"
        self.assertEquals(extract_youtube_id(url), "Hnc-1rXLx_4")


class TestVideoExists(unittest.TestCase):

    def setUp(self):
        with open(P.join(CURRENT_DIR, "config.yml")) as fin:
            self.key = yaml.load(fin)["google_developer_key"]

    def test_positive(self):
        video_id = "jNQXAC9IVRw"
        self.assertTrue(video_exists(self.key, video_id))

    def test_negative(self):
        video_id = "Y7UmFIpenjs"
        self.assertFalse(video_exists(self.key, video_id))


class TestUpload(unittest.TestCase):

    def setUp(self):
        self.up = LiveLeakUploader(True)

        with open(P.join(CURRENT_DIR, "config.yml")) as fin:
            doc = yaml.load(fin)
        self.up.login(doc["liveleak"]["username"], doc["liveleak"]["password"])

    def test_upload(self):
        path = P.join(CURRENT_DIR, "test", "foreman_cif.mp4")
        self.assertTrue(P.isfile(path))

        self.up.upload(path, "test", "test", "test", "Other")

    #
    # TODO: test upload for bad category name
    #


class TestMultipartParams(unittest.TestCase):

    def test_parse(self):
        path = P.join(CURRENT_DIR, "test", "add_item.html")
        with open(path) as fin:
            html = fin.read()
        p = extract_multipart_params(html)
        self.assertEqual(
            p["key"],
            "2014/Jul/16/LiveLeak-dot-com-2f3_1405564338-${filename}")
        self.assertEqual(
            p["Filename"],
            "LiveLeak-dot-com-2f3_1405564338-${filename}")
        self.assertEqual(p["acl"], "private")
        self.assertEqual(p["Expires"], "Thu, 01 Jan 2037 16:00:00 GMT")
        self.assertEqual(p["Content-Type"], " ")
        self.assertEqual(p["success_action_status"], "201")
        self.assertEqual(p["AWSAccessKeyId"], "AKIAIWBZFTE3KNSLSTTQ")
        self.assertEqual(
            p["policy"],
            "eyJleHBpcmF0aW9uIjoiMjAxNC0wNy0xN1QyMjozMjoxOC4wMDBaIiwiY29uZGl0\
aW9ucyI6W3siYnVja2V0IjoibGxidWNzIn0seyJhY2wiOiJwcml2YXRlIn0seyJFeHBpcmVzIjoiV\
Gh1LCAwMSBKYW4gMjAzNyAxNjowMDowMCBHTVQifSxbInN0YXJ0cy13aXRoIiwiJGtleSIsIjIwMT\
RcL0p1bFwvMTZcL0xpdmVMZWFrLWRvdC1jb20tMmYzXzE0MDU1NjQzMzgiXSxbInN0YXJ0cy13aXR\
oIiwiJENvbnRlbnQtVHlwZSIsIiJdLFsiY29udGVudC1sZW5ndGgtcmFuZ2UiLDAsIjIwOTcxNTIw\
MDAiXSx7InN1Y2Nlc3NfYWN0aW9uX3N0YXR1cyI6IjIwMSJ9LFsic3RhcnRzLXdpdGgiLCIkbmFtZ\
SIsIiJdLFsic3RhcnRzLXdpdGgiLCIkRmlsZW5hbWUiLCIiXV19")
        self.assertEqual(p["signature"], "VufnGKzbNncIeL0AMZ7nWi55FTo=")


class TestLocateVideo(unittest.TestCase):

    def test_positive(self):
        actual = locate_video(P.join(CURRENT_DIR, "test"), "foreman_cif")
        expected = P.join(CURRENT_DIR, "test", "foreman_cif.mp4")
        self.assertEqual(expected, actual)

    def test_negative(self):
        actual = locate_video(P.join(CURRENT_DIR, "test"), "not_there")
        self.assertEqual(None, actual)


def empty_db():
    engine = create_engine("sqlite:///")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


class TestCheckStale(unittest.TestCase):

    def setUp(self):
        self.bot = Bot()
        self.bot.db = empty_db()

        now = dt.datetime.now()
        hours = self.bot.hold_hours

        old_video = Video("old_video", "permalink1")
        old_video.state = State.DOWNLOADED
        old_video.discovered = now - dt.timedelta(hours=hours + 1)
        old_mention = Mention("permalink1", "old_video", "repost")
        old_mention.discovered = old_video.discovered

        new_video = Video("new_video", "permalink2")
        new_video.state = State.DOWNLOADED
        new_mention = Mention("permalink2", "new_video", "repost")

        reposted_video = Video("reposted_video", "permalink3")
        reposted_video.state = State.REPOSTED
        reposted_video.discovered = dt.datetime.min
        reposted_mention = Mention("permalink3", "reposted_video", "repost")
        reposted_mention.state = State.REPOSTED
        reposted_mention.discovered = reposted_video.discovered

        self.bot.db.add(old_video)
        self.bot.db.add(old_mention)
        self.bot.db.add(new_video)
        self.bot.db.add(new_mention)
        self.bot.db.add(reposted_video)
        self.bot.db.add(reposted_mention)
        self.bot.db.commit()

    def test(self):
        self.bot.check_stale()

        old_video = self.bot.db.query(Video)\
            .filter_by(youtubeId="old_video")\
            .one()
        self.assertEqual(old_video.state, State.STALE)
        old_mention = self.bot.db.query(Mention)\
            .filter_by(youtubeId="old_video")\
            .one()
        self.assertEqual(old_mention.state, State.STALE)

        #
        # Videos that are younger than the cutoff should not be marked as stale
        #
        new_video = self.bot.db.query(Video)\
            .filter_by(youtubeId="new_video")\
            .one()
        self.assertEqual(new_video.state, State.DOWNLOADED)
        new_mention = self.bot.db.query(Mention)\
            .filter_by(youtubeId="new_video")\
            .one()
        self.assertEqual(new_mention.state, State.DOWNLOADED)

        #
        # Reposted videos/mentions should not be marked as stale
        #
        reposted_video = self.bot.db.query(Video)\
            .filter_by(youtubeId="reposted_video")\
            .one()
        self.assertEqual(reposted_video.state, State.REPOSTED)
        reposted_mention = self.bot.db.query(Mention)\
            .filter_by(youtubeId="reposted_video")\
            .one()
        self.assertEqual(reposted_mention.state, State.REPOSTED)


class TestPurgeVideo(unittest.TestCase):

    def setUp(self):
        self.bot = Bot()
        self.bot.db = empty_db()
        video = Video("to_be_deleted", "dummy_permalink")
        video.state = State.STALE
        video.localPath = "/path/to/video.mp4"
        self.bot.db.add(video)
        self.bot.db.commit()

    def test_purge_video(self):
        video = self.bot.db.query(Video)\
            .filter_by(youtubeId="to_be_deleted")\
            .one()
        video.has_file = mock.Mock(return_value=True)

        with mock.patch("os.remove") as mock_method:
            self.bot.purge_video(video)

        mock_method.assert_called_with("/path/to/video.mp4")
        self.assertEquals(video.state, State.PURGED)

    def test_purge(self):
        video = self.bot.db.query(Video)\
            .filter_by(youtubeId="to_be_deleted")\
            .one()
        with mock.patch.object(Bot, "purge_video") as mock_method:
            self.bot.purge()
        mock_method.assert_called_with(video)
