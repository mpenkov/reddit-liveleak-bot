import unittest
import os.path as P
import datetime as dt
import json

import praw.objects

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from mock import patch, Mock

import rlb.main
from rlb.orm import Base, Video, Subreddit

CURRENT_DIR = P.dirname(P.abspath(__file__))


class TestLocateVideo(unittest.TestCase):

    def test_positive(self):
        actual = rlb.main.locate_video(CURRENT_DIR, "foreman_cif")
        expected = P.join(CURRENT_DIR, "foreman_cif.mp4")
        self.assertEqual(expected, actual)

    def test_negative(self):
        actual = rlb.main.locate_video(CURRENT_DIR, "not_there")
        self.assertEqual(None, actual)


def empty_db():
    engine = create_engine("sqlite:///")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


class TestMakeStale(unittest.TestCase):

    @patch("rlb.liveleak.Uploader")
    @patch("praw.Reddit")
    def setUp(self, mock_reddit, mock_llu):
        self.bot = rlb.main.Bot()
        self.bot.db = empty_db()

        now = dt.datetime.now()
        hours = self.bot.cfg.hold_hours

        old_video = Video("old_video", "permalink1")
        old_video.state = Video.DOWNLOADED
        old_video.discovered = now - dt.timedelta(hours=hours + 1)

        new_video = Video("new_video", "permalink2")
        new_video.state = Video.DOWNLOADED

        reposted_video = Video("reposted_video", "permalink3")
        reposted_video.state = Video.REPOSTED
        reposted_video.discovered = dt.datetime.min

        self.bot.db.add(old_video)
        self.bot.db.add(new_video)
        self.bot.db.add(reposted_video)
        self.bot.db.commit()

    def test(self):
        self.bot.make_stale()

        old_video = self.bot.db.query(Video)\
            .filter_by(youtubeId="old_video")\
            .one()
        self.assertEqual(old_video.state, Video.STALE)

        #
        # Videos that are younger than the cutoff should not be marked as stale
        #
        new_video = self.bot.db.query(Video)\
            .filter_by(youtubeId="new_video")\
            .one()
        self.assertEqual(new_video.state, Video.DOWNLOADED)

        #
        # Reposted videos/mentions should not be marked as stale
        #
        reposted_video = self.bot.db.query(Video)\
            .filter_by(youtubeId="reposted_video")\
            .one()
        self.assertEqual(reposted_video.state, Video.REPOSTED)


class TestPurgeVideo(unittest.TestCase):

    @patch("rlb.liveleak.Uploader")
    @patch("praw.Reddit")
    def setUp(self, mock_reddit, mock_uploader):
        self.bot = rlb.main.Bot()
        self.bot.db = empty_db()
        video = Video("to_be_deleted", "dummy_permalink")
        video.state = Video.STALE
        video.localPath = "/path/to/video.mp4"
        self.bot.db.add(video)
        self.bot.db.commit()

    def test_purge_video(self):
        video = self.bot.db.query(Video)\
            .filter_by(youtubeId="to_be_deleted")\
            .one()
        video.has_file = Mock(return_value=True)

        with patch("os.remove") as mock_method:
            self.bot.purge_video(video)
            mock_method.assert_called_with("/path/to/video.mp4")

        self.assertEquals(video.state, Video.PURGED)

    def test_purge(self):
        video = self.bot.db.query(Video)\
            .filter_by(youtubeId="to_be_deleted")\
            .one()
        with patch.object(rlb.main.Bot, "purge_video") as mock_method:
            self.bot.purge()
            mock_method.assert_called_with(video)


class TestDownloadVideo(unittest.TestCase):

    @patch("rlb.liveleak.Uploader")
    @patch("praw.Reddit")
    def setUp(self, mock_reddit, mock_uploader):
        self.bot = rlb.main.Bot()

        self.bot.db = empty_db()
        downloaded_video = Video("dl", "permalink1")
        downloaded_video.localPath = "dl.mp4"

    @patch("rlb.main.locate_video")
    @patch("subprocess.call")
    def test_already_downloaded(self, mock_call, mock_locate_video):
        mock_call.return_value = 0
        mock_locate_video.return_value = "dl.mp4"

        v = self.bot.download_video("dl", "permalink1")

        self.assertEquals(mock_call.called, False)
        mock_locate_video.assert_called_once_with(self.bot.cfg.dest_dir, "dl")
        self.assertEquals(v.state, Video.DOWNLOADED)

    @patch("rlb.main.locate_video")
    @patch("subprocess.call")
    def test_new(self, mock_call, mock_locate_video):
        mock_call.return_value = 0
        mock_locate_video.side_effect = [None, "dl.mp4"]

        v = self.bot.download_video("dl", "permalink1")

        self.assertEquals(mock_call.call_count, 1)
        self.assertEquals(mock_locate_video.call_count, 2)
        self.assertEquals(v.state, Video.DOWNLOADED)
        self.assertEquals(v.localPath, "dl.mp4")

    @patch("rlb.main.locate_video")
    @patch("subprocess.call")
    def test_error(self, mock_call, mock_locate_video):
        mock_call.return_value = -1
        mock_locate_video.return_value = None

        v = self.bot.download_video("dl", "permalink1")

        mock_call.assert_called_once()
        self.assertEquals(mock_locate_video.call_count, 2)
        self.assertEquals(v.localPath, None)
        self.assertEquals(v.state, Video.ERROR)


class TestBot(unittest.TestCase):

    @patch("os.makedirs")
    @patch("rlb.liveleak.Uploader")
    @patch("praw.Reddit")
    def setUp(self, mock_reddit, mock_llu, mock_makedirs):
        self.bot = rlb.main.Bot(P.join(CURRENT_DIR,
                                       "../conf/config.yml.sample"))

        self.bot.db = empty_db()

        display_name = "UkrainianConflict"
        self.subreddit = self.mock_subreddit(display_name)
        self.bot.r.get_subreddit.return_value = self.subreddit

        submissions = self.subreddit.get_new()
        self.bot.r.get_submission.return_value = submissions[0]

        info = Subreddit(display_name)
        info.mostRecentSubmission = dt.datetime(2014, 1, 1)
        info.mostRecentComment = dt.datetime(2014, 1, 1)
        self.bot.db.add(info)
        self.bot.db.commit()

        self.bot.uploader.upload.return_value = "dummy_token", "dummy_conn"
        self.bot.uploader.publish.return_value = "dummy_liveleak_id"

    @patch("praw.objects.Subreddit")
    def mock_subreddit(self, name, mock_subreddit):
        with open(P.join(CURRENT_DIR, "%s.json" % name)) as fin:
            json_dict = json.load(fin)
        subs = [praw.objects.Submission(self.bot.r, json_dict=child["data"])
                for child in json_dict["data"]["children"]]
        subreddit = mock_subreddit()
        subreddit.display_name = name
        subreddit.get_new.return_value = subs
        return subreddit

    def mock_comments(self):
        with open(P.join(CURRENT_DIR, "submission.json")) as fin:
            json_dict = json.load(fin)
        json_comments = json_dict[1]["data"]["children"]
        #
        # I'm not sure why we have to do this, but the Comment constructor
        # raises an exception if we don't create these keys.
        #
        for comment in json_comments:
            comment["_replies"] = []
            comment["name"] = "dummy"
            comment["author"] = "dummy"
        return [praw.objects.Comment(self.bot.r, json_dict=child)
                for child in json_comments]

    @patch("os.makedirs")
    @patch("rlb.liveleak.Uploader")
    @patch("praw.Reddit")
    def test_constructor(self, mock_reddit, mock_llu, mock_makedirs):
        bot = rlb.main.Bot(P.join(CURRENT_DIR, "../conf/config.yml.sample"))
        mock_makedirs.assert_called_once_with("/path/to/videos/subdir")
        bot.r.login.assert_called_once()
        bot.uploader.login.assert_called_once()

    @patch("rlb.youtube.extract_id")
    def test_download_new_videos(self, mock_eyid):
        num_submissions = len(self.subreddit.get_new())
        mock_eyid.return_value = "dQw4w9WgXcQ"
        self.bot.download_video = Mock()
        self.bot.download_new_videos("UkrainianConflict")
        self.assertEquals(mock_eyid.call_count, num_submissions)
        self.assertEquals(self.bot.download_video.call_count, num_submissions)

    def test_get_subreddit_info_known(self):
        info = self.bot.get_subreddit_info("UkrainianConflict")
        self.assertNotEquals(info.mostRecentSubmission, dt.datetime.min)

    def test_get_subreddit_info_unknown(self):
        info = self.bot.get_subreddit_info("ukraina")
        self.assertEquals(info.mostRecentSubmission, dt.datetime.min)

    def test_repost_video_give_up(self):
        video = Video("dQw4w9WgXcQ", "dummy_permalink")

        self.bot.repost_video(video)

        self.assertEquals(self.bot.uploader.upload.called, False)
        self.assertEquals(video.state, Video.STALE)

    @patch("rlb.orm.Video")
    def test_repost_video(self, mock_video):
        video = mock_video()
        video.youtubeId = "dQw4w9WgXcQ"
        video.permalink = "dummy_permalink"
        video.has_file.return_value = True
        video.liveleakId = None

        self.bot.repost_video(video)

        self.assertEquals(self.bot.uploader.upload.called, True)
        self.assertEquals(video.state, Video.REPOSTED)
        self.assertEquals(video.liveleakId, "dummy_liveleak_id")

    def test_check_replies_negative(self):
        submission = self.subreddit.get_new()[0]
        submission.comments = self.mock_comments()
        self.assertEquals(self.bot.check_replies(submission), False)

    def test_check_replies_positive(self):
        submission = self.subreddit.get_new()[0]
        submission.comments = self.mock_comments()
        submission.comments.append(praw.objects.Comment(
            self.bot.r, json_dict={"_replies": [],
                                   "author": self.bot.cfg.reddit_username,
                                   "name": "dummy"}))
        self.assertEquals(self.bot.check_replies(submission), True)

    def test_monitor(self):
        self.bot.monitor()
