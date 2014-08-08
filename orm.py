import sqlalchemy
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import ForeignKey

Base = declarative_base()

class Subreddit(Base):
    __tablename__ = "subreddits"
    id = Column(String, primary_key=True)
    mostRecentSubmission = Column(DateTime)
    mostRecentComment = Column(DateTime)
    def __repr__(self):
        return "<Submission(id=%s, mostRecentSubmission=%s, mostRecentComment=%s)>" % (`self.id`, `self.mostRecentSubmission`, `self.mostRecentComment`)

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
    def __repr__(self):
        return "<Video(id=%s, localPath=%s, liveleakId=%s)>" % (`self.youtubeId`, `self.localPath`, `self.liveleakId`)

class Mention(Base):
    __tablename__ = "mentions"
    permalink = Column(String, primary_key=True)
    youtubeId = Column(String, ForeignKey("videos.youtubeId"))
    command = Column(String)
    discovered = Column(DateTime)
    state = Column(Integer)
    def __repr__(self):
        return "<Mention(permalink=%s, youtubeId=%s, command=%s)>" % (`self.permalink`, `self.youtubeId`, `self.command`)
