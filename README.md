Bot to Repost YouTube Videos to LiveLeak
========================================

Sparked by an idea from [this thread](http://www.reddit.com/r/UkrainianConflict/comments/2auyay/gold_for_the_person_that_writes_a_bot_that_will/).

Installation
------------

On top of Python 2.7 and its default libraries, you need the following libraries:

 - [yaml](http://pyyaml.org/)
 - [lxml](http://lxml.de/)
 - [praw](https://praw.readthedocs.org/en/v2.1.16/)
 - [sqlalchemy](http://www.sqlalchemy.org/)

You also need [youtube-dl](http://rg3.github.io/youtube-dl/).

On Ubuntu, you can install these with:

    sudo apt-get install youtube-dl python-yaml python-sqlalchemy
    sudo pip install praw lxml

Update youtube-dl to the latest version:

    sudo youtube-dl -U
    sudo youtube-dl

Configuration
-------------

Edit the configuration file config.yml.
You can use config.yml.sample as a base.

Running
-------

First, create an empty database with:

    python createdb.py db.sqlite

The bot runs in two modes: monitor and repost.

    python bot.py db.sqlite monitor

In monitor mode, the bot goes through subreddits and picks out submissions with links to YouTube.
It registers these submissions in a database.
It then downloads these videos, and posts a comment asking whether this video should be reposted.
If a download fails, the bot will try again next time, up until a certain number of retries, after which it will ignore the video forever.

    python bot.py db.sqlite repost

In repost mode, the bot reposts downloaded videos to LiveLeak if they have obtained enough upvotes.

Note that the bot will not keep running after it completes its particular task.
To have it run periodically, use something like [cron](http://en.wikipedia.org/wiki/Cron).
For cron, the following lines will run the bot every 10 minutes:

    */10 * * * * python /home/misha/git/reddit-liveleak-bot/bot.py /home/misha/git/reddit-liveleak-bot/db.sqlite3 monitor
    */10 * * * * python /home/misha/git/reddit-liveleak-bot/bot.py /home/misha/git/reddit-liveleak-bot/db.sqlite3 repost

TODO
----

 - ~~Stop faking User-Agent when uploading to AWS (LiveLeaks)~~
 - ~~Proper category (News, Middle East, etc) -- currently defaulting to "World News"~~
 - Proper content rating -- currently defaulting to MA
