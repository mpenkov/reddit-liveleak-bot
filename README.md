Bot to Repost YouTube Videos to LiveLeak
========================================

Sparked by an idea from [this thread](http://www.reddit.com/r/UkrainianConflict/comments/2auyay/gold_for_the_person_that_writes_a_bot_that_will/).

Installation
------------

On top of Python 2.7 and its default libraries, you need the following libraries:

 - [lxml](http://lxml.de/)
 - [praw](https://praw.readthedocs.org/en/v2.1.16/)

You also need [youtube-dl](http://rg3.github.io/youtube-dl/).

On Ubuntu, you can install these with:

    sudo pip install praw lxml
    sudo apt-get install youtube-dl

Configuration
-------------

There are two configuration files that the bot uses: praw.ini and config.yml.
You can see sample configurations in praw.ini.sample and config.yml.sample, respectively.

Running
-------

The bot runs in three modes: monitor, download, and repost.

    python bot.py db.sqlite monitor

In monitor mode, the bot goes through subreddits and picks out submissions with links to YouTube.
It registers these submissions in a database.

    python bot.py db.sqlite download

In download mode, the bot goes through its database and downloads videos that haven't been downloaded yet.
If a download fails, the bot will try again next time, up until a certain number of retries, after which it will ignore the video forever.

    python bot.py db.sqlite repost

In repost mode, the bot reposts download videos to LiveLeak.

Note that the bot will not keep running after it completes its particular task.
To have it run periodically, use something like [cron](http://en.wikipedia.org/wiki/Cron).
