"""Upload a video to liveleak."""

import requests
import re
import mimetypes
import os.path as P
import time

from liveleak_cookies import COOKIES

def extract_multipart_params(html):
    #
    # FIXME: really fragile string search-based approach
    # Ideally, we want to parse the JavaScript and obtain the multipart_params variable.
    #
    # multipart_params: {
    #     'key': '2014/Jul/16/LiveLeak-dot-com-c9e_1405559197-${filename}', // use filename as a key
    #     'Filename': 'LiveLeak-dot-com-c9e_1405559197-${filename}', // adding this to keep consistency across the runtimes (ignored in flash mode)
    #     'acl': 'private',
    #     'Expires': 'Thu, 01 Jan 2037 16:00:00 GMT',
    #     'Content-Type': ' ', //note, leave space otherwise content-type is not passed on in flash mode
    #     'success_action_status': '201',
    #     'AWSAccessKeyId' : 'AKIAIWBZFTE3KNSLSTTQ',
    #     'policy': 'eyJleHBpcmF0aW9uIjoiMjAxNC0wNy0xN1QyMTowNjozNy4wMDBaIiwiY29uZGl0aW9ucyI6W3siYnVja2V0IjoibGxidWNzIn0seyJhY2wiOiJwcml2YXRlIn0seyJFeHBpcmVzIjoiVGh1LCAwMSBKYW4gMjAzNyAxNjowMDowMCBHTVQifSxbInN0YXJ0cy13aXRoIiwiJGtleSIsIjIwMTRcL0p1bFwvMTZcL0xpdmVMZWFrLWRvdC1jb20tYzllXzE0MDU1NTkxOTciXSxbInN0YXJ0cy13aXRoIiwiJENvbnRlbnQtVHlwZSIsIiJdLFsiY29udGVudC1sZW5ndGgtcmFuZ2UiLDAsIjIwOTcxNTIwMDAiXSx7InN1Y2Nlc3NfYWN0aW9uX3N0YXR1cyI6IjIwMSJ9LFsic3RhcnRzLXdpdGgiLCIkbmFtZSIsIiJdLFsic3RhcnRzLXdpdGgiLCIkRmlsZW5hbWUiLCIiXV19',
    #     'signature': 'NpZZGm5Fan9fOCpR47cS2lUw8e8='
    # },
    lines = [l.strip() for l in html.split("\n")]
    first_idx = last_idx = -1
    for i, line in enumerate(lines):
        if first_idx == -1:
            if line.startswith("multipart_params: {"):
                first_idx = i+1
        elif last_idx == -1:
            if line.startswith("}"):
                last_idx = i
                break
    multipart_params = {}
    for line in lines[first_idx:last_idx]:
        #
        # Get rid of JavaScript comments
        #
        try:
            line = line[:line.index("//")]
        except ValueError:
            pass
        key, value = line.split(":", 1)
        #
        # Strip quotes
        #
        key = re.sub(r"^\s*'", "", re.sub(r"'\s*$", "", key))
        value = re.sub(r"^\s*'", "", re.sub(r"',\s*$", "", value))
        multipart_params[key] = value
    return multipart_params

def mangle_filename(filename):
    #
    # This is from the add_item JavaScript
    #
    # var fixed_file_name_part = file.name.substr(0, file.name.lastIndexOf('.')) || file.name;
    # var extension = file.name.split(/[.]+/).pop().toLowerCase();
    # fixed_file_name_part = fixed_file_name_part.replace(/[^a-z0-9_-]/ig,"").replace(/\s\s*/g,"_").substr(0,40);
    # var timestamp = Math.round(+new Date()/1000);
    # up.settings.multipart_params.key = '2014/Jul/16/LiveLeak-dot-com-6e5_1405564641-'+fixed_file_name_part+'_'+timestamp.toString()+'.'+extension;
    #
    fixed_file_name_part, extension = P.splitext(filename)
    fixed_file_name_part = "".join([ch for ch in fixed_file_name_part if ch.isalnum()])
    timestamp = time.time()
    return fixed_file_name_part + "_" + str(timestamp) + extension

def upload_file(path, multipart_params):
    boundary = "----WebKitFormBoundarymNf7g3wD3ATtvrKC"
    #
    # These have to be in the right order
    #
    #fields = multipart_params.items()
    filename = P.basename(path)
    multipart_params["name"] = filename
    multipart_params["key"] = multipart_params["key"].replace("${filename}", mangle_filename(filename))
    fields = "name key Filename acl Expires Content-Type success_action_status AWSAccessKeyId policy signature".split(" ")
    fields = ((name, multipart_params[name]) for name in fields)
    files = [("file", filename, open(path, "rb").read())]
    content_type, content = encode_multipart_formdata(fields, files, boundary)
    headers = {
      "Origin": "http://www.liveleak.com",
      "Accept-Encoding": "gzip,deflate,sdch",
      "Host": "llbucs.s3.amazonaws.com",
      "Accept-Language": "en-US,en;q=0.8,ja;q=0.6,ru;q=0.4",
      "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.153 Safari/537.36",
      "Content-Type": content_type,
      "Accept": "*/*",
      "Referer": "http://www.liveleak.com/item?a=add_item",
      "Connection": "keep-alive",
      "Content-Length": len(content)
    }

    url = "https://llbucs.s3.amazonaws.com/"
    r = requests.post(url, cookies=COOKIES, headers=headers, data=content)
    print r.status_code
    with open("response.html", "w") as fout:
        fout.write(r.text)

#
# Taken from http://code.activestate.com/recipes/146306/
# http://stackoverflow.com/questions/1270518/python-standard-library-to-post-multipart-form-data-encoded-data
#
def encode_multipart_formdata(fields, files, boundary):
    """
    fields is a sequence of (name, value) elements for regular form fields.
    files is a sequence of (name, filename, value) elements for data to be uploaded as files
    Return (content_type, body) ready for httplib.HTTP instance
    """
    CRLF = '\r\n'
    L = []
    for (key, value) in fields:
        L.append('--' + boundary)
        L.append('Content-Disposition: form-data; name="%s"' % key)
        L.append('')
        L.append(value)
    for (key, filename, value) in files:
        L.append('--' + boundary)
        L.append('Content-Disposition: form-data; name="%s"; filename="%s"' % (key, filename))
        L.append('Content-Type: %s' % get_content_type(filename))
        L.append('')
        L.append(value)
    L.append('--' + boundary + '--')
    L.append('')
    body = CRLF.join(L)
    content_type = 'multipart/form-data; boundary=%s' % boundary
    return content_type, body

def get_content_type(filename):
    return mimetypes.guess_type(filename)[0] or 'application/octet-stream'

with open("test/add_item.html") as fin:
    html = fin.read()
multipart_params = extract_multipart_params(html)
import sys
upload_file(sys.argv[1], multipart_params)
