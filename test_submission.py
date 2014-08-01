"""Post a new submission to /r/redditliveleakbot."""
import datetime
from bot import Bot

bot = Bot()
bot.r.login(bot.reddit_username, bot.reddit_password)

subreddit = bot.r.get_subreddit("redditliveleakbot")
submission = subreddit.submit("Test %s" % datetime.datetime.now().isoformat(), url="http://youtu.be/wTAJ4u-vRp4", save=True)
print submission
