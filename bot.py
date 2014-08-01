import praw
import re
import sqlite3
import datetime
import subprocess as sub
import os
import os.path as P
import yaml
import traceback
import urllib
import re
import collections

#
# TODO: logging
# http://blog.tplus1.com/blog/2007/09/28/the-python-logging-module-is-much-better-than-print-statements/
#

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import NoResultFound

from orm import Submission, Mention, Video
from liveleak_upload import LiveLeakUploader
from user_agent import USER_AGENT

STATE_DISCOVERED = 1
STATE_DOWNLOADED = 2
STATE_REPOSTED = 3
STATE_STALE = 4

MENTION_REGEX = re.compile(r"redditliveleakbot \+(?P<command>\w+)", re.IGNORECASE)

COMMENT = """[**Mirror**](http://www.liveleak.com/view?i=%s) 

---

^| [^Feedback](http://www.reddit.com/r/redditliveleakbot/) ^| [^FAQ](http://www.reddit.com/r/redditliveleakbot/wiki/index) ^|"""

def extract_youtube_id(url):
    """Extract a YouTube ID from a URL."""
    m = re.search(r"youtu\.?be.*(v=|/)(?P<id>[a-zA-Z0-9-_]{11})&?", url)
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

        self.liveleak_username = doc["liveleak"]["username"]
        self.liveleak_password = doc["liveleak"]["password"]
        self.liveleak_dummy = doc["liveleak"]["dummy"]
        self.reddit_username = doc["reddit"]["username"]
        self.reddit_password = doc["reddit"]["password"]

        self.ups_threshold = doc["ups_threshold"]
        self.hold_hours = doc["hold_hours"]
        self.subreddits = doc["subreddits"]

        engine = create_engine(doc["dbpath"])
        Session = sessionmaker(bind=engine)
        self.session = Session()

        self.r = praw.Reddit(USER_AGENT)
        self.r.login(self.reddit_username, self.reddit_password)

    def monitor(self):
        """Monitor all subreddits specified in the config.xml file."""
        for subreddit in self.subreddits:
            self.monitor_submissions(subreddit)
            self.download()
            self.monitor_mentions(subreddit)
            self.monitor_summons(subreddit)

    def monitor_submissions(self, subreddit):
        """Monitors the specific subreddit for submissions that link to YouTube videos."""
        submissions = self.r.get_subreddit(subreddit).get_new(limit=self.limit)
        for new_submission in submissions:
            try:
                submission = self.session.query(Submission).filter_by(id=new_submission.id).one()
                break
            except NoResultFound:
                print "new_submission", new_submission
                submission = Submission(id=new_submission.id, subreddit=subreddit, title=new_submission.title, discovered=datetime.datetime.now())
                self.session.add(submission)
                self.session.commit()

            youtube_id = extract_youtube_id(new_submission.url)
            if youtube_id == None:
                print "skipping submission URL:", new_submission.url
                continue

            try:
                video = self.session.query(Video).filter_by(youtubeId=youtube_id).one()
            except NoResultFound:
                video = Video(youtubeId=youtube_id, state=STATE_DISCOVERED, downloadAttempts=0, lastModified=datetime.datetime.now())
                self.session.add(video)

            submission.youtubeId = youtube_id
            self.session.commit()

    def monitor_mentions(self, subreddit):
        """Monitor the specific subreddits for comments that mention our username."""
        for new_comment in self.r.get_subreddit(subreddit).get_comments(limit=self.limit):
            m = MENTION_REGEX.search(new_comment.body)
            if not m:
                continue
            try:
                mention = self.session.query(Mention).filter_by(permalink=new_comment.permalink).one()
                break
            except NoResultFound:
                #
                # TODO: check that we've seen the parent submission and have downloaded the video from YouTube
                #
                mention = Mention(permalink=new_comment.permalink, submissionId=new_comment.submission.id, discovered=datetime.datetime.now(), command=m.group("command"), state=STATE_DISCOVERED)
                print mention.permalink, mention.command
                self.session.add(mention)
                self.session.commit()

    def monitor_summons(self, subreddit):
        submission_comments = collections.defaultdict(list)
        for mention in self.session.query(Mention).filter_by(state=STATE_DISCOVERED):
            comment = self.r.get_submission(mention.permalink).comments[0]
            submission_comments[comment.submission].append(comment)

        uploader = LiveLeakUploader()
        uploader.login(self.liveleak_username, self.liveleak_password)

        for submission in submission_comments:
            score = sum([x.ups-x.downs for x in submission_comments[submission]])
            print submission, score
            if score < self.ups_threshold:
                continue

            try:
                old_submission, video = self.session.query(Submission, Video).filter(Submission.id==submission.id).filter(Submission.youtubeId==Video.youtubeId).filter_by(id=submission.id).one()
            except NoResultFound:
                #
                # This will happen if 
                #
                # 1) we haven't seen the submission before or 
                # 2) the submission doesn't have a link to a YouTube video
                #
                continue

            if video.state != STATE_DOWNLOADED:
                #
                # This will happen if
                #
                # 1) The video hasn't been downloaded yet
                # 2) The video has already been reposted
                #
                continue

            body = "repost of http://youtube.com/watch?v=%s from %s" % (video.youtubeId, submission.permalink)
            print body
            try:
                if self.liveleak_dummy:
                    liveleak_id = "dummy"
                else:
                    liveleak_id = uploader.upload(video.localPath, submission.title, body, subreddit, self.subreddits[subreddit])
            except:
                print traceback.format_exc()
                break

            video.liveleakId = liveleak_id
            video.state = STATE_REPOSTED
            for mention in self.session.query(Mention).filter_by(submissionId=submission.id):
                mention.state = STATE_REPOSTED
            self.session.commit()

            submission_comments[submission][0].reply(COMMENT % liveleak_id)

    def download(self):
        """Downloads videos that have not yet been downloaded."""
        for video in self.session.query(Video).filter_by(state=STATE_DISCOVERED):
            video.downloadAttempts += 1
            video.lastModified = datetime.datetime.now()
            self.session.commit()

            template = P.join(self.dest_dir, "%(id)s.%(ext)s")
            args = ["youtube-dl", "--quiet", "--output", template, "--", video.youtubeId]
            return_code = sub.call(args)
            print " ".join(args)
            if return_code != 0:
                print "download failed for YouTube video ID:", video.youtubeId
                continue

            #
            # TODO: is there a better way to work out what the local file name is?
            # We know the ID but don't know the extension
            #
            video.localPath = None
            for f in os.listdir(self.dest_dir):
                if f.startswith(video.youtubeId):
                    video.localPath = P.join(self.dest_dir, f)
                    break
            assert video.localPath
            video.state = STATE_DOWNLOADED
            self.session.commit()

    def check_stale(self):
        """Make all data that hasn't been updated in self.hold_hours hours stale."""
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=self.hold_hours)
        for mention in self.session.query(Mention).filter_by(state=STATE_DISCOVERED):
            if mention.discovered < cutoff:
                mention.state = STATE_STALE

        for video in self.session.query(Video):
            if video.lastModified < cutoff and video.state != STATE_REPOSTED:
                video.state = STATE_STALE
                video.lastModified = datetime.datetime.now()

        self.session.commit()

    def purge(self):
        """Delete stale video data."""
        for video in self.session.query(Video).filter_by(state=STATE_STALE):
            if P.isfile(video.localPath):
                print "removing", video.localPath
                try:
                    os.remove(video.localPath)
                except OSError:
                    print traceback.format_exc()
                    pass

            video.localPath = None
            video.state = STATE_PURGED
            video.lastModified = datetime.datetime.now()

def create_parser(usage):
    """Create an object to use for the parsing of command-line arguments."""
    from optparse import OptionParser
    parser = OptionParser(usage)
    parser.add_option("-c", "--config", dest="config", type="string", default=None, help="Specify the configuration file to use")
    return parser

def main():
    parser = create_parser("usage: %s action [options]" % __file__)
    options, args = parser.parse_args()
    if len(args) != 1:
        parser.error("invalid number of arguments")
    action = args[0]
    if action not in "monitor check_stale purge".split(" "):
        parser.error("invalid action: %s" % action)

    bot = Bot(options.config)
    if action == "monitor":
        bot.monitor()
    elif action == "check_stale":
        bot.check_stale()
    elif action == "purge":
        bot.purge()
    else:
        assert False, "not implemented yet"

if __name__ == "__main__":
    main()
