import base64
import json
import re
import tempfile
import traceback
import urllib.parse
import yt_dlp

max_result_length = 6291556
def result_length(r):
    return len(json.dumps(r, ensure_ascii=False).encode())

def youtube(url, log=None):
    if log is None:
        log = {}
    log['url'] = url

    data = {'url': url}

    sub_preferences_en = ['en', 'en-US', 'en-GB', 'en-AU', 'en-CA', 'en-IN', 'en-IE']
    sub_preferences_zh = ['zh-CN', 'zh-Hans', 'zh', 'zh-Hant', 'zh-TW', 'zh-HK', 'zh-SG']
    autosub_preferences = ['en']

    with yt_dlp.YoutubeDL() as ydl:
        info = ydl.extract_info(url, download=False, process=False)

        if 'title' in info:
            data['title'] = info['title']
            log['title'] = info['title']
        if 'channel' in info:
            data['channel'] = info['channel']
            log['channel'] = info['channel']
        if 'uploader' in info:
            data['uploader'] = info['uploader']
            log['uploader'] = info['uploader']
        if 'uploader' in data and 'channel' in data:
            if data['uploader'] == data['channel']:
                del data['uploader']
                del log['uploader']
        if 'description' in info:
            data['description'] = info['description']

        if 'title' in info and len([c for c in info['title'] if ord(c) in range(0x3400, 0xa000)]) >= 5:
            sub_preferences = sub_preferences_zh + sub_preferences_en
            log['guess_lang'] = 'zh'
        else:
            sub_preferences = sub_preferences_en + sub_preferences_zh
            log['guess_lang'] = 'en'

        log['subtitles'] = list(info['subtitles'])
        log['automatic_captions'] = list(info['automatic_captions'])
        subtitle = None
        for lang in sub_preferences:
            if lang in info['subtitles']:
                subtitle = 'sub', lang
                break
        if subtitle is None:
            for lang in info['subtitles']:
                if lang != 'live_chat':
                    subtitle = 'sub', lang
                    break
        if subtitle is None:
            for lang in autosub_preferences:
                if lang in info['automatic_captions']:
                    subtitle = 'autosub', lang
                    break

        if subtitle is None:
            raise ValueError('No subtitle found')
    log['subtitle_type'] = subtitle[0]
    log['subtitle_lang'] = subtitle[1]

    with tempfile.TemporaryDirectory() as tmpdir:
        options = {
            'outtmpl': f'{tmpdir}/output.%(ext)s',
            'skip_download': True,
            'subtitleslangs': [subtitle[1]],
            'subtitlesformat': 'json3',
        }
        if subtitle[0] == 'sub':
            options['writesubtitles'] = True
        elif subtitle[0] == 'autosub':
            options['writeautomaticsub'] = True

        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])

        with open(f'{tmpdir}/output.{subtitle[1]}.json3') as f:
            json3 = json.load(f)
            subtitle_lines = []
            for event in json3['events']:
                if 'segs' in event:
                    line = ''.join([seg['utf8'] for seg in event['segs']]).strip()
                    if line:
                        subtitle_lines.append(line)

    transcript = '\n'.join(subtitle_lines)

    print(json.dumps(log, ensure_ascii=False, indent=2))

    result = {
        'data': data,
        'truncated': False,
        'template': [
            {'field': 'url', 'name': 'URL', 'type': 'inline'},
            {'field': 'title', 'name': 'Title', 'type': 'inline'},
            {'field': 'channel', 'name': 'Channel', 'type': 'inline'},
            {'field': 'uploader', 'name': 'Uploader', 'type': 'inline'},
            {'field': 'description', 'name': 'Description', 'type': 'block'},
            {'field': 'transcript', 'name': 'Transcript', 'type': 'block'},
        ],
    }
    result['data']['transcript'] = transcript
    if result_length(result) > max_result_length:
        result['truncated'] = True
        result['data']['transcript'] = ''
        left = 0
        right = len(transcript)
        while left + 1 < right:
            mid = (left + right) // 2
            result['data']['transcript'] = transcript[:mid]
            if result_length(result['data']) > max_result_length:
                right = mid
            else:
                left = mid
        result['data']['transcript'] = transcript[:left]
    return result


def handler(event, context):
    content_type = event['headers'].get('content-type', '')

    if content_type == 'application/json':
        body = json.loads(event['body'])
    elif content_type == 'application/x-www-form-urlencoded':
        if event['isBase64Encoded']:
            body_str = base64.b64decode(event['body']).decode('utf-8')
        else:
            body_str = event['body']
        body = urllib.parse.parse_qs(body_str)
    else:
        return {
            'statusCode': 400,
            'body': 'Unsupported content type'
        }

    # Extract URL from the body.
    # The exact key used to extract the URL might vary depending on the request structure.
    url = body.get('url')
    if not url:
        return {
            'statusCode': 400,
            'body': 'URL not found in the request'
        }
    elif isinstance(url, list):
        url = url[0]

    return youtube(url, {'event': event, 'context': repr(context)})
