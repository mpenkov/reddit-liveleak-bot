#!/usr/bin/env python
from rlb.main import Bot


def create_parser(usage):
    """Create an object to use for the parsing of command-line arguments."""
    from optparse import OptionParser
    parser = OptionParser(usage)
    parser.add_option(
        "-c", "--config", dest="config", type="string",
        default=None, help="Specify the configuration file to use")
    return parser


def main():
    parser = create_parser("usage: %s action [options]" % __file__)
    options, args = parser.parse_args()
    if len(args) != 1:
        parser.error("invalid number of arguments")
    action = args[0]
    if action not in "monitor deleted check_stale purge".split(" "):
        parser.error("invalid action: %s" % action)

    bot = Bot(options.config)
    if action == "monitor":
        bot.monitor()
    elif action == "purge":
        bot.purge()
    else:
        assert False, "not implemented yet"

if __name__ == "__main__":
    main()
