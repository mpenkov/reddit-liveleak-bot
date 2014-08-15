import praw
import re
import sqlite3
import datetime as dt
import subprocess as sub
import os
import os.path as P
import yaml
import traceback
import urllib
import re
import collections
import logging

#
# http://blog.tplus1.com/blog/2007/09/28/the-python-logging-module-is-much-better-than-print-statements/
#
logging.basicConfig(level=logging.INFO)
#
# http://stackoverflow.com/questions/11029717/how-do-i-disable-log-messages-from-the-requests-library
#
requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import NoResultFound

from orm import Subreddit, Mention, Video
from orm import STATE_DOWNLOADED, STATE_REPOSTED, STATE_STALE
from liveleak_upload import LiveLeakUploader
from user_agent import USER_AGENT
from video_exists import video_exists

MENTION_REGEX = re.compile(
    r"redditliveleakbot \+(?P<command>\w+)", re.IGNORECASE)

COMMENT_MIRROR = "[**Mirror**](http://www.liveleak.com/view?i=%s)"
COMMENT_ERROR = "**Error:** %s"
COMMENT_FOOTER = """

---

^| [^Feedback](http://www.reddit.com/r/redditliveleakbot/)
^| [^FAQ](http://www.reddit.com/r/redditliveleakbot/wiki/index) ^|"""


class VideoUnavailableException(Exception):
    pass


def transaction(func):
    """Wrap up a function call as a transaction.
    If the transaction succeeds, commit the session.
    If something goes wrong, roll the session back.
    Returns whatever the inner method returned on success,
    or None on failure."""
    def inner(self, *args, **kwargs):
        try:
            ret = func(self, *args, **kwargs)
            self.session.commit()
            return ret
        except Exception as ex:
            logging.exception(ex)
            self.session.rollback()
            return None
    return inner


def locate_video(subdir, video_id):
    for f in os.listdir(subdir):
        if f.startswith(video_id):
            return P.join(subdir, f)


def extract_youtube_id(url):
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


class Bot(object):
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = P.join(P.dirname(P.abspath(__file__)), "config.yml")
        with open(config_path) as fin:
            doc = yaml.load(fin)
        self.limit = int(doc["limit"])
        self.dest_dir = doc["videopath"]

        if not P.isdir(self.dest_dir):
            os.makedirs(self.dest_dir)

        #
        # TODO: check the correctness of the config file
        #
        self.liveleak_username = doc["liveleak"]["username"]
        self.liveleak_password = doc["liveleak"]["password"]
        self.liveleak_dummy = doc["liveleak"]["dummy"]
        self.reddit_username = doc["reddit"]["username"]
        self.reddit_password = doc["reddit"]["password"]
        self.google_developer_key = doc["google_developer_key"]

        self.ups_threshold = doc["ups_threshold"]
        self.hold_hours = doc["hold_hours"]
        self.subreddits = doc["subreddits"]

        engine = create_engine(doc["dbpath"])
        Session = sessionmaker(bind=engine)
        self.session = Session()

        self.r = praw.Reddit(USER_AGENT)
        self.r.login(self.reddit_username, self.reddit_password)

        self.uploader = LiveLeakUploader()
        self.uploader.login(self.liveleak_username, self.liveleak_password)

    def monitor(self):
        """Monitor all subreddits specified in the config.xml file."""
        for subreddit in self.subreddits:
            if self.subreddits[subreddit]["download_all"]:
                self.download_new_videos(subreddit)
            self.monitor_mentions(subreddit)
            self.try_repost(subreddit)
            self.monitor_deleted_videos()

    @transaction
    def get_subreddit_info(self, sr):
        try:
            sub_info = self.session.query(Subreddit).filter_by(id=sr).one()
        except NoResultFound:
            sub_info = Subreddit(id=sr)
            self.session.add(sub_info)
        return sub_info

    def download_new_videos(self, subreddit):
        """Monitors the specific subreddit for new submissions that
        link to YouTube videos."""
        meth_name = "download_new_videos"
        sub_info = self.get_subreddit_info(subreddit)

        now = dt.datetime.now()

        for new_submission in self.r.get_subreddit(
                subreddit).get_new(limit=self.limit):
            created = dt.datetime.fromtimestamp(new_submission.created_utc)
            if created < sub_info.mostRecentSubmission:
                break

            youtube_id = extract_youtube_id(new_submission.url)
            if youtube_id is None:
                logging.debug("skipping submission URL: %s",
                              new_submission.url)
                continue

            logging.info("%s: new video submission: %s %s", meth_name,
                         new_submission.permalink, new_submission.url)

            try:
                video = self.session.query(Video).filter_by(
                    youtubeId=youtube_id).one()
                if video.localPath is None or not P.isfile(video.localPath):
                    raise NoResultFound("need to download this video again")
            except NoResultFound:
                self.download_video(youtube_id, new_submission.permalink)

        sub_info.mostRecentSubmission = now
        self.session.commit()

    def monitor_mentions(self, subreddit):
        """Monitor the specific subreddits for comments that mention
        our username."""
        meth_name = "monitor_mentions"
        sub_info = self.get_subreddit_info(subreddit)

        now = dt.datetime.now()

        for new_comment in self.r.get_subreddit(
                subreddit).get_comments(limit=self.limit):
            created = dt.datetime.fromtimestamp(new_comment.created_utc)
            if created < sub_info.mostRecentComment:
                break

            m = MENTION_REGEX.search(new_comment.body)
            if not m:
                continue

            if self.check_replies(new_comment):
                continue

            #
            # TODO: If the bot starts getting overwhelmed, do the
            # downloading AFTER we're checking for upvotes
            #
            youtube_id = extract_youtube_id(new_comment.submission.url)
            if youtube_id is None:
                self.reply_error(
                    new_comment, "[this](%s) is not a YouTube video",
                    new_comment.submission.url)
                logging.error("%s: could not extract youtube_id from URL: %s",
                              meth_name, new_comment.submission.url)
                continue

            #
            # First, check if we've already downloaded this video.
            # If we haven't, then download it.
            # Notify the poster of any problems during downloading.
            #
            try:
                video = self.session.query(Video).filter_by(
                    youtubeId=youtube_id).one()
                if video.liveleakId:
                    logger.info(
                        "%s: this video has already been reposted: %s",
                        meth_name, youtube_id)
                    self.reply_success(new_comment, video.liveleakId)
                    continue
                elif video.localPath is None or not P.isfile(video.localPath):
                    raise NoResultFound("need to download this video again")
                assert P.isfile(video.localPath)
            except NoResultFound:
                video = self.download_video(
                    youtube_id, new_comment.submission.permalink)
                if video is None:
                    url = new_comment.submission.url
                    self.reply_error(
                        new_comment, "couldn't download [this video](%s)", url)
                    continue

            mention = Mention(new_comment.permalink, youtube_id,
                              m.group("command"))
            self.session.add(mention)
            self.session.commit()

        sub_info.mostRecentComment = now
        self.session.commit()

    def try_repost(self, subreddit):
        """Monitor currently active Mentions for instances when the bot
        should be summoned."""
        meth_name = "try_repost"
        submission_comments = collections.defaultdict(list)
        for mention in self.session.query(Mention).filter_by(
                state=STATE_DOWNLOADED):
            comment = self.r.get_submission(
                mention.permalink).comments[0]
            #
            # TODO: this is a bit hacky
            #
            comment.mention = mention
            submission_comments[comment.submission].append(comment)

        for submission in submission_comments:
            score = sum([x.score for x in submission_comments[submission]])
            logging.debug("%s: %d %s", meth_name,
                          submission.score, submission.permalink)
            if score < self.ups_threshold:
                continue

            youtube_id = submission_comments[submission][0].mention.youtubeId
            #
            # The query below can never fail since the
            # Mention.state is DOWNLOADED
            #
            video = self.session.query(Video).filter_by(
                youtubeId=youtube_id).one()
            assert P.isfile(video.localPath)

            self.repost_requested_video(video, submission_comments[submission])

    @transaction
    def repost_requested_video(self, video, comments):
        self.repost_video(video)
        for comment in comments:
            comment.mention.state = STATE_REPOSTED
            self.reply_success(comment, video.liveleakId)

    @transaction
    def download_video(self, youtube_id, permalink):
        """Download the video with the specified YouTube ID.
        If it has already been downloaded, the actual download is skipped.
        Returns a Video instance.
        """
        meth_name = "download_video"
        try:
            video = self.session.query(Video).filter_by(
                youtubeId=youtube_id).one()
        except NoResultFound:
            video = Video(youtube_id, permalink)
            self.session.add(video)

        video.localPath = locate_video(self.dest_dir, video.youtubeId)

        if video.localPath is None:
            template = P.join(self.dest_dir, "%(id)s.%(ext)s")
            args = ["youtube-dl", "--quiet", "--output",
                    template, "--", video.youtubeId]
            logging.debug("%s: %s", meth_name, " ".join(args))
            return_code = sub.call(args)
            logging.debug("%s: return_code: %d", meth_name, return_code)
            if return_code != 0:
                raise VideoUnavailableException(
                    "download failed for video: %s" % video.youtubeId)
            video.localPath = locate_video(self.dest_dir, video.youtubeId)

        assert video.localPath

        video.state = STATE_DOWNLOADED
        video.downloaded = dt.datetime.now()
        video.localModified = dt.datetime.now()
        return video

    @transaction
    def check_stale(self):
        """Make all data that hasn't been updated in self.hold_hours
        hours stale."""
        cutoff = dt.datetime.now() - dt.timedelta(hours=self.hold_hours)
        for mention in self.session.query(Mention).filter_by(
                state=STATE_DOWNLOADED):
            if mention.discovered < cutoff:
                mention.state = STATE_STALE

        for video in self.session.query(Video):
            if video.discovered < cutoff and video.state != STATE_REPOSTED:
                video.state = STATE_STALE
                video.localModified = dt.datetime.now()

    def purge(self):
        """Delete stale video data."""
        for video in self.session.query(Video).filter_by(state=STATE_STALE):
            purge_video(video)

    @transaction
    def purge_video(self, video):
        if P.isfile(video.localPath):
            logging.debug("removing %s", video.localPath)
            try:
                os.remove(video.localPath)
            except OSError as ose:
                logging.exception(ose)
                pass

        video.localPath = None
        video.state = STATE_PURGED
        video.localModified = dt.datetime.now()

    def repost_video(self, video):
        """Repost the video to LiveLeak.
        Raises Exceptions on failure.
        Returns None."""
        meth_name = "repost_video"
        submission = self.r.get_submission(video.redditSubmissionPermalink)
        subreddit = submission.subreddit.display_name
        body = "repost of http://youtube.com/watch?v=%s from %s" % (
            video.youtubeId, submission.permalink)
        logging.info("%s: %s", meth_name, body)
        if self.liveleak_dummy:
            liveleak_id = "dummy"
        else:
            liveleak_id = self.uploader.upload(
                video.localPath, submission.title, body, subreddit,
                self.subreddits[subreddit]["liveleak_category"])
        video.liveleakId = liveleak_id
        video.state = STATE_REPOSTED

    def check_replies(self, thing):
        """Return true if we've replied to the submission/comment already.

        Ideally, we shouldn't have to check for this over the wire, since
        our database should be sufficient.  However, it avoids embarrassing
        multi-posts in some cases, e.g. database has been reset."""
        meth_name = "check_replies"
        if isinstance(thing, praw.objects.Submission):
            replies = thing.comments
        elif isinstance(thing, praw.objects.Comment):
            replies = thing.replies
        else:
            raise ValueError("unexpected thing: %s" % thing.__class__.__name__)
        reply_authors = [r.author.name for r in replies if r.author]
        result = "redditliveleakbot" in reply_authors
        if result:
            logging.info(
                "%s: we have already replied to this thing: %s", meth_name,
                thing.permalink)
        return result

    def monitor_deleted_videos(self):
        """Go through all our downloaded videos and check if they have
        been deleted from YouTube.  If yes, repost them."""
        for video in self.session.query(Video).filter_by(
                state=STATE_DOWNLOADED):
            if video_exists(self.google_developer_key, video.youtubeId):
                continue
            submission = self.r.get_submission(video.redditSubmissionPermalink)
            if self.check_replies(submission):
                continue
            self.repost_deleted_video(video, submission)

    @transaction
    def repost_deleted_video(self, video, submission):
        self.repost_video(video)
        #
        # Technically, there could be comments summoning the bot as well.
        # Should we reply to them instead?
        #
        submission.add_comment(self.make_comment_repost(video.liveleakId))
        video.deleted = dt.datetime.now()

    def reply_success(self, thing, liveleak_id):
        if isinstance(thing, praw.objects.Submission):
            fun = thing.comment
        elif isinstance(thing, praw.objects.Comment):
            fun = thing.reply
        else:
            assert False
        comment = (COMMENT_MIRROR % liveleak_id) + COMMENT_FOOTER
        fun(comment)

    def reply_error(self, thing, formatstr, *args):
        if isinstance(thing, praw.objects.Submission):
            fun = thing.comment
        elif isinstance(thing, praw.objects.Comment):
            fun = thing.reply
        else:
            assert False
        comment = (COMMENT_ERROR % (formatstr % args)) + COMMENT_FOOTER
        fun(comment)


def create_parser(usage):
    """Create an object to use for the parsing of command-line arguments."""
    from optparse import OptionParser
    parser = OptionParser(usage)
    parser.add_option(
        "-c", "--config", dest="config", type="string",
        default=None, help="Specify the configuration file to use")
    return parser


def main():
    parser = create_parser("usage: %s action [options]" % __file__)
    options, args = parser.parse_args()
    if len(args) != 1:
        parser.error("invalid number of arguments")
    action = args[0]
    if action not in "monitor deleted check_stale purge".split(" "):
        parser.error("invalid action: %s" % action)

    bot = Bot(options.config)
    if action == "monitor":
        bot.monitor()
    elif action == "deleted":
        bot.monitor_deleted_videos()
    elif action == "check_stale":
        bot.check_stale()
    elif action == "purge":
        bot.purge()
    else:
        assert False, "not implemented yet"

if __name__ == "__main__":
    main()
