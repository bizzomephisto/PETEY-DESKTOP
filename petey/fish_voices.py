"""Read Fish Audio's paginated voice catalog; credentials never leave the server."""
import json

import requests

from petey.fish_tts import FishTTS, FishTTSError, validate_voice_id
from petey.http_client import SESSION as HTTP_SESSION

PAGE_SIZE = 50
MAX_RESPONSE = 2 * 1024 * 1024


def list_fish_voices(ai_config, query='', scope='public', page=1):
    if not isinstance(query, str) or len(query) > 100:
        raise ValueError('Search names must be at most 100 characters.')
    if scope not in ('public', 'mine') or type(page) is not int or not 1 <= page <= 200:
        raise ValueError('Choose Public voices or My voices and a page between 1 and 200.')
    key = FishTTS(ai_config).api_key
    if not key:
        raise FishTTSError('Add a Fish Audio key under Models & API keys before browsing voices.')
    params = {'page_size': PAGE_SIZE, 'page_number': page, 'self': 'true' if scope == 'mine' else 'false', 'sort_by': 'score'}
    if query.strip():
        params['title'] = query.strip()
    response = None
    try:
        response = HTTP_SESSION.get('https://api.fish.audio/model',
            headers={'Authorization': f'Bearer {key}', 'Accept': 'application/json'},
            params=params, timeout=(10, 20), allow_redirects=False, stream=True)
        if response.status_code != 200:
            raise FishTTSError(f'Fish Audio voice catalog returned HTTP {response.status_code}. Check the API key and try again.')
        body = bytearray()
        for chunk in response.iter_content(65536):
            body.extend(chunk)
            if len(body) > MAX_RESPONSE:
                raise FishTTSError('Fish Audio voice catalog response was too large. Try a narrower search.')
        payload = json.loads(body)
    except requests.RequestException as error:
        raise FishTTSError('Could not reach the Fish Audio voice catalog. Check the connection and try again.') from error
    except (ValueError, TypeError) as error:
        raise FishTTSError('Fish Audio returned an invalid voice catalog response.') from error
    finally:
        if response is not None:
            response.close()
    if not isinstance(payload, dict) or not isinstance(payload.get('items'), list):
        raise FishTTSError('Fish Audio returned an invalid voice catalog response.')
    voices, seen = [], set()
    for item in payload['items'][:PAGE_SIZE]:
        if not isinstance(item, dict) or item.get('dmca_taken_down') is True:
            continue
        try:
            identifier = validate_voice_id(item.get('_id', ''))
        except ValueError:
            continue
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        author = item.get('author') if isinstance(item.get('author'), dict) else {}
        languages = item.get('languages') if isinstance(item.get('languages'), list) else []
        voices.append({'id': identifier, 'name': str(item.get('title') or identifier)[:200],
                       'author': str(author.get('nickname') or '')[:100],
                       'languages': [value[:40] for value in languages[:10] if isinstance(value, str)]})
    total = payload.get('total')
    total = total if type(total) is int and total >= 0 else None
    more = payload.get('has_more')
    if type(more) is not bool:
        more = page * PAGE_SIZE < total if total is not None else len(payload['items']) >= PAGE_SIZE
    return {'voices': voices, 'page': page, 'has_more': more and page < 200,
            'total': total, 'scope': scope}
