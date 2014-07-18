import praw
import re
import sqlite3
import datetime
import subprocess as sub
import os
import os.path as P
import yaml

from liveleak_upload import LiveLeakUploader

def extract_youtube_id(url):
    """Extract a YouTube ID from a URL."""
    m = re.search(r"youtube.com/watch\?v=(?P<id>\w{11})", url)
    if m:
        return m.group("id")
    return None

class Bot(object):
    def __init__(self, dbpath, dest_dir, limit):
        self.r = praw.Reddit("Mirror YouTube videos to LiveLeak by u/mishapenkov v 0.1\nURL: https://github.com/mpenkov/reddit-liveleak-bot")
        self.r.login()
        self.limit = limit
        self.conn = sqlite3.connect(dbpath)
        self.dest_dir = dest_dir

        if not P.isdir(self.dest_dir):
            os.makedirs(self.dest_dir)

        with open(P.join(P.dirname(P.abspath(__file__)), "config.yml")) as fin:
            doc = yaml.load(fin)

        self.liveleak_username = doc["liveleak"]["username"]
        self.liveleak_password = doc["liveleak"]["password"]


    def monitor(self, subreddit):
        """Monitors the specific subreddit for submissions that link to YouTube videos."""
        c = self.conn.cursor()
        submissions = self.r.get_subreddit(subreddit).get_top(limit=self.limit)
        for submission in submissions:
            if c.execute("SELECT id FROM RedditSubmissions WHERE id = ?", (submission.id,)).fetchone():
                print "skipping submission ID:", submission.id
                continue

            c.execute("INSERT INTO RedditSubmissions VALUES (?, ?)", (submission.id, datetime.datetime.now()))

            youtube_id = extract_youtube_id(submission.url)
            if youtube_id == None:
                print "skipping submission URL:", submission.url
                continue

            if c.execute("SELECT youTubeId FROM Videos WHERE youTubeId = ?", (youtube_id,)).fetchone():
                print "skipping YouTube video ID:", youtube_id
                continue

            c.execute("INSERT INTO Videos VALUES (?, NULL, NULL, ?, ?, ?, 0)", (youtube_id, submission.id, subreddit, submission.title))
        c.close()
        self.conn.commit()

    def download(self):
        """Downloads videos that have not yet been downloaded."""
        c = self.conn.cursor()
        for (youtube_id, attempts) in c.execute("""SELECT youTubeId, downloadAttempts 
            FROM Videos 
            WHERE LocalPath IS NULL AND downloadAttempts < 3""").fetchall():
            template = P.join(self.dest_dir, "%(id)s.%(ext)s")
            args = ["youtube-dl", youtube_id, "--quiet", "--output", template]
            return_code = sub.call(args)
            print " ".join(args)
            if return_code != 0:
                print "download failed for YouTube video ID:", youtube_id
                cc = self.conn.cursor()
                cc.execute("UPDATE Videos SET downloadAttempts = ? WHERE youTubeId = ?", (attempts+1, youtube_id))
                continue
            #
            # TODO: is there a better way to work out what the local file name is?
            # We know the ID but don't know the extension
            #
            dest_file = None
            for f in os.listdir(self.dest_dir):
                if f.startswith(youtube_id):
                    dest_file = P.join(self.dest_dir, f)
            if dest_file:
                c.execute("UPDATE Videos SET LocalPath = ? WHERE youTubeId = ?", (dest_file, youtube_id))
        c.close()
        self.conn.commit()

    def repost(self):
        c = self.conn.cursor()
        uploader = LiveLeakUploader()
        uploader.login(self.liveleak_username, self.liveleak_password)
        for (youtube_id, local_path, subreddit, title) in c.execute("""SELECT youTubeId, localPath, subreddit, redditTitle
            FROM Videos 
            WHERE LocalPath IS NOT NULL AND LiveLeakId IS NULL"""):
            #
            # TODO: handle exceptions on upload
            #
            item_token = uploader.upload(local_path, title, "reposted from YouTube ID: " + youtube_id, subreddit)
            c.execute("UPDATE Videos SET liveLeakId = ? WHERE youTubeId = ?", (item_token, youtube_id))

            #
            # TODO: post a comment under the original entry
            #


def create_parser(usage):
    """Create an object to use for the parsing of command-line arguments."""
    from optparse import OptionParser
    parser = OptionParser(usage)
    parser.add_option("-l", "--limit", dest="limit", type="int", default="10", help="Set the limit for fetching submissions when monitoring")
    parser.add_option("-d", "--dest-dir", dest="dest_dir", type="string", default=None, help="Specify the destination directory for downloaded videos")
    return parser

def main():
    parser = create_parser("usage: %s file.sqlite3 action [options]" % __file__)
    options, args = parser.parse_args()
    if len(args) != 2:
        parser.error("invalid number of arguments")
    dbpath, action = args
    if action not in "monitor download repost".split(" "):
        parser.error("invalid action: %s" % action)

    dest_dir = options.dest_dir if options.dest_dir else P.join(P.dirname(P.abspath(__file__)), "videos")

    bot = Bot(dbpath, dest_dir, options.limit)
    if action == "monitor":
        for subreddit in "UkrainianConflict ukraina".split(" "):
            bot.monitor(subreddit)
    elif action == "download":
        bot.download()
    elif action == "repost":
        bot.repost()
    else:
        assert False, "not implemented yet"


if __name__ == "__main__":
    main()
