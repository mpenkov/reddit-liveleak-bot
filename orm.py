import sqlalchemy
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import ForeignKey

Base = declarative_base()

class Submission(Base):
    __tablename__ = "submissions"
    id = Column(String, primary_key=True)
    subreddit = Column(String)
    title = Column(String)
    youtubeId = Column(String, ForeignKey("videos.youtubeId"))
    discovered = Column(DateTime)
    def __repr__(self):
        return "<Submission(id=%s, subreddit=%s, youtubeId=%s)>" % (`self.id`, `self.subreddit`, `self.youtubeId`)

class Video(Base):
    __tablename__ = "videos"
    youtubeId = Column(String, primary_key=True)
    downloadAttempts = Column(Integer)
    localPath = Column(String)
    liveleakId = Column(String)
    state = Column(Integer)
    lastModified = Column(DateTime)
    def __repr__(self):
        return "<Video(id=%s, localPath=%s, liveleakId=%s)>" % (`self.youtubeId`, `self.localPath`, `self.liveleakId`)

class Mention(Base):
    __tablename__ = "mentions"
    permalink = Column(String, primary_key=True)
    submissionId = Column(String, ForeignKey("submissions.id"))
    command = Column(String)
    discovered = Column(DateTime)
    state = Column(Integer)
    def __repr__(self):
        return "<Mention(id=%s, submissionId=%s, command=%s)>" % (`self.permalink`, `self.submissionId`, `self.command`)
