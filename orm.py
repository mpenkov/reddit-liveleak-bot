import datetime
import sqlalchemy
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import ForeignKey

Base = declarative_base()

STATE_DOWNLOADED = 2
STATE_REPOSTED = 3
STATE_STALE = 4


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
        return "<Submission(id=%s, mostRecentSubmission=%s,\
mostRecentComment=%s)>" % (repr(self.id), repr(self.mostRecentSubmission),
                           repr(self.mostRecentComment))


class Video(Base):
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


class Mention(Base):
    __tablename__ = "mentions"
    permalink = Column(String, primary_key=True)
    youtubeId = Column(String, ForeignKey("videos.youtubeId"))
    command = Column(String)
    discovered = Column(DateTime)
    state = Column(Integer)

    def __init__(self, permalink, youtube_id, command):
        self.permalink = permalink
        self.youtubeId = youtube_id
        self.command = command
        self.discovered = datetime.datetime.now()
        self.state = STATE_DOWNLOADED

    def __repr__(self):
        return "<Mention(permalink=%s, youtubeId=%s, command=%s)>" % (
            repr(self.permalink), repr(self.youtubeId), repr(self.command))
