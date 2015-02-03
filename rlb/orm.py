import os.path as P
import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Subreddit(Base):
    __tablename__ = "subreddits"
    id = Column(String, primary_key=True)
    mostRecentSubmission = Column(DateTime)
    mostRecentComment = Column(DateTime)

    def __init__(self, id):
        self.id = id
        self.mostRecentSubmission = datetime.datetime.min
        self.mostRecentComment = datetime.datetime.min

    def __repr__(self):
        return "<Subreddit(id=%s, mostRecentSubmission=%s,\
mostRecentComment=%s)>" % (repr(self.id), repr(self.mostRecentSubmission),
                           repr(self.mostRecentComment))


class Video(Base):
    DOWNLOADED = 2
    REPOSTED = 3
    STALE = 4
    ERROR = 5
    PURGED = 6

    __tablename__ = "videos"
    youtubeId = Column(String, primary_key=True)
    redditSubmissionPermalink = Column(String)
    downloadAttempts = Column(Integer)
    localPath = Column(String)
    liveleakId = Column(String)
    state = Column(Integer)
    discovered = Column(DateTime)
    localModified = Column(DateTime)
    deleted = Column(DateTime)

    def __init__(self, youtube_id, permalink):
        self.youtubeId = youtube_id
        self.redditSubmissionPermalink = permalink
        self.discovered = datetime.datetime.now()

    def __repr__(self):
        return "<Video(id=%s, localPath=%s, liveleakId=%s)>" % (
            repr(self.youtubeId), repr(self.localPath), repr(self.liveleakId))

    def has_file(self):
        return self.localPath and P.isfile(self.localPath)
