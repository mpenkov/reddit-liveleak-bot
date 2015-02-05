#!/usr/bin/env python
import rlb.youtube
import sys
import logging
logging.basicConfig(level=logging.INFO)
rlb.youtube.download(".", sys.argv[1])
