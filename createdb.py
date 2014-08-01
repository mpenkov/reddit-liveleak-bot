"""Create an empty SQLite database."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from orm import Base

def create_parser():
    from optparse import OptionParser
    p = OptionParser("usage: %prog db.sqlite3")
    return p

def main():
    p = create_parser()
    opts, args = p.parse_args()
    if len(args) != 1:
        p.error("invalid number of arguments")
    fname = args[0]
    answer = raw_input("This will reset the database %s. Are you sure? " % fname)
    if answer != "yes":
        print "Aborting."
        return
    open(fname, "w").close()
    engine = create_engine("sqlite:///"+fname)
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()
    session.commit()

if __name__ == "__main__":
    main()
