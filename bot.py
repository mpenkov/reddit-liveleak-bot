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

COMMENT = """Hi!
I'm a bot.

I've downloaded [this video](%(video_url)s) and am considering reposting it to [LiveLeak](http://www.liveleak.com) in case it gets deleted from YouTube later on.
Do you think it is worth reposting?
If yes, please let me know by upvoting this comment.
If no, please let me know by downvoting this comment.

If I repost videos that I shouldn't repost, I'll get in trouble!
Please don't let me repost such videos, for example:

 - Videos that have been already posted to LiveLeak. Please [check](http://www.liveleak.com/browse?%(querystring)s) first!
 - Videos that I obviously don't own copyright for (e.g. VICE News)
 - Videos that aren't interesting enough
 - Videos that aren't controversial and are thus unlikely to ever be deleted

Thank you!

If there's any sort of problem, please do not hesitate to contact [my master](https://github.com/mpenkov/reddit-liveleak-bot/issues)."""

UPDATED_COMMENT = "\n\n**EDIT**: The people have spoken! The mirror is [here](http://www.liveleak.com/view?i=%s)."

"""The minimum number of upvotes in order to consider reposting."""
UPS_THRESHOLD = 10

HOLD_HOURS = 48

def extract_youtube_id(url):
    """Extract a YouTube ID from a URL."""
    m = re.search(r"youtu\.?be.*(v=|/)(?P<id>[a-zA-Z0-9-_]{11})&?", url)
    if m:
        return m.group("id")
    return None

class Bot(object):
    def __init__(self, dbpath, dest_dir, limit):
        self.limit = limit
        self.conn = sqlite3.connect(dbpath)
        self.dest_dir = dest_dir

        if not P.isdir(self.dest_dir):
            os.makedirs(self.dest_dir)

        with open(P.join(P.dirname(P.abspath(__file__)), "config.yml")) as fin:
            doc = yaml.load(fin)

        self.liveleak_username = doc["liveleak"]["username"]
        self.liveleak_password = doc["liveleak"]["password"]
        self.reddit_username = doc["reddit"]["username"]
        self.reddit_password = doc["reddit"]["password"]

        self.r = praw.Reddit("Mirror YouTube videos to LiveLeak by u/mishapenkov v 1.0\nURL: https://github.com/mpenkov/reddit-liveleak-bot")
        self.r.login(self.reddit_username, self.reddit_password)

    def monitor(self, subreddit):
        """Monitors the specific subreddit for submissions that link to YouTube videos."""
        c = self.conn.cursor()
        submissions = self.r.get_subreddit(subreddit).get_top(limit=self.limit)
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=HOLD_HOURS)
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
            args = ["youtube-dl", youtube_id, "--quiet", "--output", template]
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
                submission.add_comment(COMMENT % {"video_url": "http://youtu.be/%s" % youtube_id, "querystring": urllib.urlencode([("q", title)])})

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
            if not comment.body.startswith(COMMENT[:10]):
                continue
            if comment.ups-comment.downs > UPS_THRESHOLD:
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
                body = "repost of http://youtube.com/watch?v=%s from %s" % (youtube_id, submission.url)
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
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=HOLD_HOURS)
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

            print "removing", local_path
            os.remove(local_path)

def create_parser(usage):
    """Create an object to use for the parsing of command-line arguments."""
    from optparse import OptionParser
    parser = OptionParser(usage)
    parser.add_option("-l", "--limit", dest="limit", type="int", default="100", help="Set the limit for fetching submissions when monitoring")
    parser.add_option("-d", "--dest-dir", dest="dest_dir", type="string", default=None, help="Specify the destination directory for downloaded videos")
    return parser

def main():
    parser = create_parser("usage: %s file.sqlite3 action [options]" % __file__)
    options, args = parser.parse_args()
    if len(args) != 2:
        parser.error("invalid number of arguments")
    dbpath, action = args
    if action not in "monitor repost purge".split(" "):
        parser.error("invalid action: %s" % action)

    dest_dir = options.dest_dir if options.dest_dir else P.join(P.dirname(P.abspath(__file__)), "videos")

    bot = Bot(dbpath, dest_dir, options.limit)
    if action == "monitor":
        for subreddit in ["UkrainianConflict"]:
            bot.monitor(subreddit)
        bot.download()
    elif action == "repost":
        bot.repost()
    elif action == "purge":
        bot.purge()
    else:
        assert False, "not implemented yet"

if __name__ == "__main__":
    main()
