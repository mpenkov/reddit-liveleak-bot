Bot to Repost YouTube Videos to LiveLeak
========================================

Sparked by an idea from [this thread](http://www.reddit.com/r/UkrainianConflict/comments/2auyay/gold_for_the_person_that_writes_a_bot_that_will/).

Also see [/r/redditliveleakbot](http://www.reddit.com/r/redditliveleakbot/).

Installation
------------

On top of Python 2.7 and its default libraries, you need the following libraries:

 - [yaml](http://pyyaml.org/)
 - [lxml](http://lxml.de/)
 - [praw](https://praw.readthedocs.org/en/v2.1.16/)
 - [sqlalchemy](http://www.sqlalchemy.org/)
 - [requests](http://docs.python-requests.org/)
 - [requests-toolbelt](http://toolbelt.readthedocs.org/)

You also need [youtube-dl](http://rg3.github.io/youtube-dl/).

On Ubuntu, you can install these with:

    sudo apt-get install youtube-dl python-yaml python-sqlalchemy
    sudo pip install praw lxml requests requests-toolbelt

Update youtube-dl to the latest version:

    sudo youtube-dl -U
    sudo youtube-dl

Configuration
-------------

Edit the configuration file and save it as rlb/conf/config.yml.
You can use rlb/conf/config.yml.sample as a base.

Running
-------

First, create an empty database with:

    python bin/createdb.py db.sqlite3

Set the absolute path to this database in rlb/conf/config.yml.

The bot runs in two modes: monitor and purge.

    bin/bot.sh monitor

In monitor mode, the bot goes through subreddits and picks out submissions with links to YouTube.
It downloads the videos and registers them in a database.
If also checks if videos that are already present in the database are still available through YouTube, and if they're not, reposts them to LiveLeak.

    bin/bot.sh purge

In purge mode, the bot deletes videos that have been in the database for a specific amount of time (to save disk space).

Note that the bot will not keep running after it completes its particular task.
To have it run periodically, use something like [cron](http://en.wikipedia.org/wiki/Cron).
For cron, the following line will monitor every hour and purge every week, respectively:

    0  * * * * cd /path/to/bot && PYTHONPATH="." bin/bot.py monitor
    55 * * * 0 cd /path/to/bot && PYTHONPATH="." bin/bot.py purge
