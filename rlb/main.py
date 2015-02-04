import praw
from praw.errors import APIException
import datetime as dt
import os
import os.path as P
import yaml
import logging
import time

#
# http://blog.tplus1.com/blog/2007/09/28/the-python-logging-module-is-much-better-than-print-statements/
#
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#
# http://stackoverflow.com/questions/11029717/how-do-i-disable-log-messages-from-the-requests-library
#
requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import NoResultFound

import liveleak
import youtube
from orm import Subreddit, Video

COMMENT_MIRROR = "[**Mirror**](http://www.liveleak.com/view?i=%s)"
COMMENT_FOOTER = """

---

^| [^Feedback](http://www.reddit.com/r/redditliveleakbot/)
^| [^FAQ](http://www.reddit.com/r/redditliveleakbot/wiki/index) ^|"""


def transaction(func):
    """Wrap up a function call as a transaction.
    If the transaction succeeds, commit the session.
    If something goes wrong, roll the session back.
    Returns whatever the inner method returned on success,
    or None on failure."""
    def inner(self, *args, **kwargs):
        try:
            ret = func(self, *args, **kwargs)
            self.db.commit()
            return ret
        except Exception as ex:
            logger.exception(ex)
            self.db.rollback()
            return None
    return inner


def error_prone_praw_api_call(func):
    """Used to decorate the most error-prone PRAW API calls.

    For example, commenting on a submission can fail if the submission has
    been deleted."""
    def inner(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except APIException as ex:
            logger.exception(ex)
            return None
    return inner


def locate_video(subdir, video_id):
    for f in os.listdir(subdir):
        if f.startswith(video_id):
            return P.join(subdir, f)


class Config(object):

    def __init__(self, config_path=None):
        if config_path is None:
            config_path = P.join(P.dirname(P.abspath(__file__)),
                                 "conf/config.yml")

        with open(config_path) as fin:
            doc = yaml.load(fin)

        self.limit = int(doc["limit"])
        self.dest_dir = doc["videopath"]
        self.user_agent = doc["user_agent"]
        self.liveleak_username = doc["liveleak"]["username"]
        self.liveleak_password = doc["liveleak"]["password"]
        self.reddit_username = doc["reddit"]["username"]
        self.reddit_password = doc["reddit"]["password"]
        self.google_developer_key = doc["google_developer_key"]

        self.hold_hours = doc["hold_hours"]
        self.category = {}
        for sub in doc["subreddits"]:
            self.category[sub] = doc["subreddits"][sub]["liveleak_category"]
        self.dbpath = doc["dbpath"]


class Bot(object):

    def __init__(self, config_path=None):

        self.cfg = Config(config_path)
        if not P.isdir(self.cfg.dest_dir):
            os.makedirs(self.cfg.dest_dir)

        engine = create_engine(self.cfg.dbpath)
        Session = sessionmaker(bind=engine)
        self.db = Session()

        self.r = praw.Reddit(self.cfg.user_agent)
        self.r.login(self.cfg.reddit_username, self.cfg.reddit_password)

        self.uploader = liveleak.Uploader(self.cfg.user_agent)
        self.uploader.login(self.cfg.liveleak_username,
                            self.cfg.liveleak_password)

    def monitor(self):
        """Monitor all subreddits specified in the config.xml file."""
        for subreddit in self.subreddits:
            self.download_new_videos(subreddit)
        self.monitor_deleted_videos()

    @transaction
    def get_subreddit_info(self, sr):
        try:
            sub_info = self.db.query(Subreddit).filter_by(id=sr).one()
        except NoResultFound:
            sub_info = Subreddit(id=sr)
            self.db.add(sub_info)
        return sub_info

    def download_new_videos(self, subreddit):
        """Monitors the specific subreddit for new submissions that
        link to YouTube videos."""
        meth_name = "download_new_videos"
        sub_info = self.get_subreddit_info(subreddit)

        now = dt.datetime.now()

        for new_submission in self.r.get_subreddit(
                subreddit).get_new(limit=self.cfg.limit):
            created = dt.datetime.fromtimestamp(new_submission.created_utc)
            if created < sub_info.mostRecentSubmission:
                break

            youtube_id = youtube.extract_id(new_submission.url)
            logger.debug("%s: youtube_id: %s", meth_name, youtube_id)
            if youtube_id is None:
                logger.debug("skipping submission URL: %s",
                             new_submission.url)
                continue

            logger.info("%s: new video submission: %s %s %s", meth_name,
                        new_submission.permalink, new_submission.url,
                        youtube_id)

            download = True
            try:
                v = self.db.query(Video).filter_by(youtubeId=youtube_id).one()
                download = not v.has_file()
            except NoResultFound:
                pass
            if download:
                self.download_video(youtube_id, new_submission.permalink)

        sub_info.mostRecentSubmission = now
        self.db.commit()

    @transaction
    def download_video(self, youtube_id, permalink):
        """Download the video with the specified YouTube ID.
        If it has already been downloaded, the actual download is skipped.
        Returns a Video instance.
        """
        try:
            v = self.db.query(Video).filter_by(youtubeId=youtube_id).one()
        except NoResultFound:
            v = Video(youtube_id, permalink)
            self.db.add(v)

        v.localPath = locate_video(self.cfg.dest_dir, v.youtubeId)

        if v.localPath is None:
            youtube.download(self.cfg.dest_dir, v.youtubeId)
            v.localPath = locate_video(self.cfg.dest_dir, v.youtubeId)

        if v.localPath is None:
            v.state = Video.ERROR
        else:
            v.state = Video.DOWNLOADED
            v.downloaded = dt.datetime.now()
            v.localModified = dt.datetime.now()
        return v

    @transaction
    def make_stale(self):
        """Make all data that hasn't been updated in self.hold_hours
        hours stale."""
        cutoff = dt.datetime.now() - dt.timedelta(hours=self.cfg.hold_hours)
        for video in self.db.query(Video).filter_by(state=Video.DOWNLOADED):
            if video.discovered is None or video.discovered < cutoff:
                video.state = Video.STALE
                video.localModified = dt.datetime.now()

    def purge(self):
        """Delete stale and reposted video data."""
        for video in self.db.query(Video).filter_by(state=Video.STALE):
            self.purge_video(video)
        for video in self.db.query(Video).filter_by(state=Video.REPOSTED):
            self.purge_video(video)
        for video in self.db.query(Video):
            if not video.has_file():
                self.purge_video(video)

    @transaction
    def purge_video(self, video):
        if video.has_file():
            logger.info("removing %s", video.localPath)
            try:
                os.remove(video.localPath)
            except OSError as ose:
                logger.exception(ose)

        video.localPath = None
        video.state = Video.PURGED
        video.localModified = dt.datetime.now()

    @transaction
    def repost_video(self, video):
        meth_name = "repost_video"
        submission = self.r.get_submission(video.redditSubmissionPermalink)
        subreddit = submission.subreddit.display_name
        body = "repost of http://youtube.com/watch?v=%s from %s" % (
            video.youtubeId, submission.permalink)
        logger.info("%s: %s", meth_name, body)
        if not video.has_file():
            #
            # If we're reposting, then the video has already been deleted from
            # YouTube.  If we don't have the video downloaded by now, there's
            # nothing we can do.
            #
            logger.info("%s: giving up on %s", meth_name, video.youtubeId)
            video.state = Video.STALE
        elif video.liveleakId is None:
            category = self.cfg.category[subreddit]
            logger.debug("%s: category: %s", meth_name, category)

            file_token, connection = self.uploader.upload(video.localPath)
            video.liveleakId = self.uploader.publish(submission.title, body,
                                                     subreddit, category,
                                                     connection)
            video.state = Video.REPOSTED

    def check_replies(self, submission):
        """Return true if we've replied to the submission already.

        Ideally, we shouldn't have to check for this over the wire, since
        our database should be sufficient.  However, it avoids embarrassing
        multi-posts in some cases, e.g. database has been reset."""
        meth_name = "check_replies"
        reply_authors = [r.author.name for r in submission.comments
                         if r.author]
        result = self.cfg.reddit_username in reply_authors
        if result:
            logger.info("%s: we have already replied to this submission: %s",
                        meth_name, submission.permalink)
        return result

    def monitor_deleted_videos(self):
        """Go through all our downloaded videos and check if they have
        been deleted from YouTube.  If yes, repost them."""
        for v in self.db.query(Video).filter_by(state=Video.DOWNLOADED):
            try:
                if youtube.video_exists(v.youtubeId, self.cfg.user_agent,
                                        self.cfg.google_developer_key):
                    continue
            except youtube.YoutubeException:
                time.sleep(5)
                continue

            submission = self.r.get_submission(v.redditSubmissionPermalink)
            if self.check_replies(submission):
                continue

            self.repost_video(v)
            if v.liveleakId is None:
                continue

            self.post_comment(submission, v.liveleakId)
            v.deleted = dt.datetime.now()
            self.db.commit()

    @error_prone_praw_api_call
    def post_comment(self, submission, liveleak_id):
        comment = (COMMENT_MIRROR % liveleak_id) + COMMENT_FOOTER
        submission.add_comment(comment)
