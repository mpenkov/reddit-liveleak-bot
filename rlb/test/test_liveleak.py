import unittest
import os.path as P

import rlb.main
import rlb.liveleak

CURRENT_DIR = P.dirname(P.abspath(__file__))


class TestUpload(unittest.TestCase):

    def setUp(self):
        config = rlb.main.Config()
        self.up = rlb.liveleak.Uploader(config.user_agent)
        self.up.login(config.liveleak_username, config.liveleak_password)
        self.path = P.join(CURRENT_DIR, "foreman_cif.mp4")
        self.assertTrue(P.isfile(self.path))

    def test_upload(self):
        file_token, _ = self.up.upload(self.path)
        self.up.delete(file_token)

    #
    # TODO: test upload for bad category name
    #


class TestMultipartParams(unittest.TestCase):

    def test_parse(self):
        path = P.join(CURRENT_DIR, "add_item.html")
        with open(path) as fin:
            html = fin.read()
        p = rlb.liveleak.extract_multipart_params(html)
        self.assertEqual(
            p["key"],
            "2014/Jul/16/LiveLeak-dot-com-2f3_1405564338-${filename}")
        self.assertEqual(
            p["Filename"],
            "LiveLeak-dot-com-2f3_1405564338-${filename}")
        self.assertEqual(p["acl"], "private")
        self.assertEqual(p["Expires"], "Thu, 01 Jan 2037 16:00:00 GMT")
        self.assertEqual(p["Content-Type"], " ")
        self.assertEqual(p["success_action_status"], "201")
        self.assertEqual(p["AWSAccessKeyId"], "AKIAIWBZFTE3KNSLSTTQ")
        self.assertEqual(
            p["policy"],
            "eyJleHBpcmF0aW9uIjoiMjAxNC0wNy0xN1QyMjozMjoxOC4wMDBaIiwiY29uZGl0\
aW9ucyI6W3siYnVja2V0IjoibGxidWNzIn0seyJhY2wiOiJwcml2YXRlIn0seyJFeHBpcmVzIjoiV\
Gh1LCAwMSBKYW4gMjAzNyAxNjowMDowMCBHTVQifSxbInN0YXJ0cy13aXRoIiwiJGtleSIsIjIwMT\
RcL0p1bFwvMTZcL0xpdmVMZWFrLWRvdC1jb20tMmYzXzE0MDU1NjQzMzgiXSxbInN0YXJ0cy13aXR\
oIiwiJENvbnRlbnQtVHlwZSIsIiJdLFsiY29udGVudC1sZW5ndGgtcmFuZ2UiLDAsIjIwOTcxNTIw\
MDAiXSx7InN1Y2Nlc3NfYWN0aW9uX3N0YXR1cyI6IjIwMSJ9LFsic3RhcnRzLXdpdGgiLCIkbmFtZ\
SIsIiJdLFsic3RhcnRzLXdpdGgiLCIkRmlsZW5hbWUiLCIiXV19")
        self.assertEqual(p["signature"], "VufnGKzbNncIeL0AMZ7nWi55FTo=")
