"""Create an empty SQLite database."""
import sqlite3
import os
import os.path as P

def create_parser(usage):
    """Create an object to use for the parsing of command-line arguments."""
    from optparse import OptionParser
    parser = OptionParser(usage)
    return parser

def main():
    parser = create_parser("usage: %s file.sqlite3 [options]" % __file__)
    options, args = parser.parse_args()
    if len(args) != 1:
        parser.error("invalid number of arguments")
    dbpath = args[0]

    if P.isfile(dbpath):
        os.remove(dbpath)

    conn = sqlite3.connect(dbpath)
    c = conn.cursor()

    c.execute("CREATE TABLE redditSubmissions (id TEXT PRIMARY KEY, discovered DATETIME)")
    c.execute("""CREATE TABLE videos (
            youtubeId TEXT PRIMARY KEY NOT NULL,
            localPath TEXT,
            liveleakId TEXT,
            redditSubmissionId TEXT NOT NULL,
            subreddit TEXT NOT NULL,
            redditTitle TEXT NOT NULL,
            downloadAttempts INTEGER,
            notified DATETIME,
            FOREIGN KEY (redditSubmissionId) REFERENCES redditSubmissions(id)
        )""")
    c.close()
    conn.commit()

if __name__ == "__main__":
    main()
