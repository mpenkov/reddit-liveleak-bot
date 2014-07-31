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

from liveleak_upload import LiveLeakUploader

COMMENT = """Should I repost this video to LiveLeak?
Upvote for "yes"; downvote for "no" (if unsure, read the [FAQ](http://www.reddit.com/r/redditliveleakbot/wiki/index#wiki_q.3A_what_kind_of_videos_should_not_be_reposted.3F))."""

UPDATED_COMMENT = "\n\n**EDIT**: The mirror is [here](http://www.liveleak.com/view?i=%s)."

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
        self.reddit_username = doc["reddit"]["username"]
        self.reddit_password = doc["reddit"]["password"]

        self.hold_hours = int(doc["hold_hours"])
        self.subreddits = doc["subreddits"]

        self.conn = sqlite3.connect(doc["dbpath"])

        self.r = praw.Reddit("Mirror YouTube videos to LiveLeak by u/mishapenkov v 1.0\nURL: https://github.com/mpenkov/reddit-liveleak-bot")
        self.r.login(self.reddit_username, self.reddit_password)

    def monitor(self):
        """Monitor all subreddits."""
        for subreddit in self.subreddits:
            self.monitor_subreddit(subreddit)

    def monitor_subreddit(self, subreddit):
        """Monitors the specific subreddit for submissions that link to YouTube videos."""
        c = self.conn.cursor()
        submissions = self.r.get_subreddit(subreddit).get_top(limit=self.limit)
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=self.hold_hours)
        for submission in submissions:
            #
            # Ignore items older than HOLD_HOURS hours
            #
            if datetime.datetime.fromtimestamp(submission.created_utc) < cutoff:
                continue
            if c.execute("SELECT id FROM RedditSubmissions WHERE id = ?", (submission.id,)).fetchone():
                #print "skipping submission ID:", submission.id
                continue

            c.execute("INSERT INTO RedditSubmissions VALUES (?, ?)", (submission.id, datetime.datetime.now()))

            youtube_id = extract_youtube_id(submission.url)
            if youtube_id == None:
                print "skipping submission URL:", submission.url
                continue

            if c.execute("SELECT youTubeId FROM Videos WHERE youTubeId = ?", (youtube_id,)).fetchone():
                #print "skipping YouTube video ID:", youtube_id
                continue

            c.execute("INSERT INTO Videos VALUES (?, NULL, NULL, ?, ?, ?, 0, NULL)", (youtube_id, submission.id, subreddit, submission.title))

        c.close()
        self.conn.commit()

    def download(self):
        """Downloads videos that have not yet been downloaded."""
        c = self.conn.cursor()
        for (youtube_id, submission_id, title, attempts) in c.execute("""SELECT youTubeId, redditSubmissionId, redditTitle, downloadAttempts
            FROM Videos
            WHERE LocalPath IS NULL AND downloadAttempts < 3""").fetchall():

            cc = self.conn.cursor()
            cc.execute("UPDATE Videos SET downloadAttempts = ? WHERE youTubeId = ?", (attempts+1, youtube_id))

            template = P.join(self.dest_dir, "%(id)s.%(ext)s")
            args = ["youtube-dl", "--quiet", "--output", template, "--", youtube_id]
            return_code = sub.call(args)
            print " ".join(args)
            if return_code != 0:
                print "download failed for YouTube video ID:", youtube_id
                continue

            #
            # TODO: is there a better way to work out what the local file name is?
            # We know the ID but don't know the extension
            #
            dest_file = None
            for f in os.listdir(self.dest_dir):
                if f.startswith(youtube_id):
                    dest_file = P.join(self.dest_dir, f)
                    break

            if dest_file:
                c.execute("UPDATE Videos SET LocalPath = ? WHERE youTubeId = ?", (dest_file, youtube_id))
                submission = self.r.get_submission(submission_id=submission_id)
                submission.add_comment(COMMENT % {"video_url": "http://youtu.be/%s" % youtube_id, "querystring": urllib.urlencode([("q", title.encode("utf-8"))])})

        c.close()
        self.conn.commit()

    def repost(self):
        """Go through all our comments.
        Find the videos that people want reposted the most.
        Repost them.
        Notify once successful."""
        me = self.r.get_redditor(self.reddit_username)
        comments = {}
        for comment in me.get_comments():
            #
            # TODO: why doesn't the comment text match completely here?
            #
            #print comment.submission.id, comment.submission.title[:10], comment.ups-comment.downs
            if comment.ups-comment.downs > self.ups_threshold:
                comments[comment.submission.id] = comment

        c = self.conn.cursor()
        uploader = LiveLeakUploader()
        uploader.login(self.liveleak_username, self.liveleak_password)

        for submission_id in sorted(comments, key=lambda x: comments[x].ups-comments[x].downs, reverse=True):
            #
            # TODO: do we really need the notified field?
            #
            row = c.execute("""
                SELECT youTubeId, liveLeakId, localPath, subreddit, redditTitle
                FROM Videos
                WHERE LocalPath IS NOT NULL AND redditSubmissionId = ? AND notified IS NULL""", (submission_id,)).fetchone()

            if row == None:
                continue
            youtube_id, liveleak_id, local_path, subreddit, title = row

            if not liveleak_id:
                submission = self.r.get_submission(submission_id=submission_id)
                body = "repost of http://youtube.com/watch?v=%s from %s" % (youtube_id, submission.permalink)
                print body
                try:
                    liveleak_id = uploader.upload(local_path, title, body, subreddit)
                except:
                    print traceback.format_exc()
                    break
                c.execute("UPDATE Videos SET liveLeakId = ? WHERE youTubeId = ?", (liveleak_id, youtube_id))

            print "reposted", liveleak_id

            updated_text = comments[submission_id].body + (UPDATED_COMMENT % liveleak_id)
            comments[submission_id].edit(updated_text)

            c.execute("UPDATE Videos SET notified = ? WHERE youTubeId = ?", (datetime.datetime.now(), youtube_id))

        c.close()
        self.conn.commit()

    def purge(self):
        """Remove all data older than HOLD_HOURS hours from the database and the hard disk."""
        old_submissions = []
        c = self.conn.cursor()
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=self.hold_hours)
        for (submission_id, discovered) in c.execute("SELECT id, discovered FROM redditSubmissions").fetchall():
            #
            # 2014-07-20 00:40:26.489840
            #
            if datetime.datetime.strptime(discovered, "%Y-%m-%d %H:%M:%S.%f") < cutoff:
                old_submissions.append(submission_id)
                #print submission_id, discovered

        #
        # TODO: keep this mapping in the videos table of the DB
        #
        me = self.r.get_redditor(self.reddit_username)
        comments = {}
        for comment in me.get_comments():
            if comment.body.startswith(COMMENT[:10]):
                comments[comment.submission.id] = comment

        for submission_id in old_submissions:
            row = c.execute("SELECT localPath, liveLeakId FROM videos WHERE redditSubmissionId = ?", (submission_id,)).fetchone()
            if row is None:
                continue
            local_path, liveleak_id = row

            #
            # Remove comments for that submission if there was no repost to LiveLeak
            #
            if liveleak_id is None:
                try:
                    comment = comments[submission_id]
                    comment.delete()
                    print "deleting comment", comment.ups-comment.downs
                except KeyError:
                    continue

            c.execute("DELETE FROM videos WHERE redditSubmissionId = ?", (submission_id,))
            c.execute("DELETE FROM redditSubmissions WHERE id = ?", (submission_id,))

            #
            # TODO: in theory, multiple submissions can link to the same video
            # How to handle this properly?
            #
            if P.isfile(local_path):
                print "removing", local_path
                try:
                    os.remove(local_path)
                except OSError:
                    print traceback.format_exc()
                    pass

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
    if action not in "monitor repost purge".split(" "):
        parser.error("invalid action: %s" % action)

    bot = Bot(options.config)
    if action == "monitor":
        bot.monitor()
        bot.download()
    elif action == "repost":
        bot.repost()
    elif action == "purge":
        bot.purge()
    else:
        assert False, "not implemented yet"

if __name__ == "__main__":
    main()
