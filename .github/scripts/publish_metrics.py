"""Publish only metric JSON using the trusted job's short-lived GitHub token."""
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    repo, source = os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_SHA']
    branch = os.environ['DEFAULT_BRANCH']

    def api(method, path, payload=None):
        request = Request('https://api.github.com/repos/'+repo+'/'+path,
                          data=None if payload is None else json.dumps(payload).encode(),
                          method=method, headers={'Authorization': 'Bearer '+os.environ['GH_TOKEN'],
                          'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json'})
        with urlopen(request, timeout=30) as response:
            return json.load(response)

    if api('GET', 'commits/'+branch)['sha'] != source:
        print('Skipping metrics from an older source revision.')
        return
    payloads = {name: json.loads((Path('badge-data')/name).read_text())
                for name in ['tests.json', 'coverage.json']}
    payloads['source.json'] = {'commit': source,
        'run_url': f"https://github.com/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"}
    try:
        parent = api('GET', 'git/ref/heads/badges')['object']['sha']
    except HTTPError as exc:
        if exc.code != 404:
            raise
        parent = None
    tree = api('POST', 'git/trees', {'tree': [
        {'path': name, 'mode': '100644', 'type': 'blob', 'content': json.dumps(value, indent=2)+'\n'}
        for name, value in payloads.items()]})
    commit = api('POST', 'git/commits', {'message': 'Update CI metrics for '+source[:12],
        'tree': tree['sha'], 'parents': [parent] if parent else []})
    # No force-push: an unexpected concurrent publisher must fail, not overwrite.
    if parent:
        api('PATCH', 'git/refs/heads/badges', {'sha': commit['sha'], 'force': False})
    else:
        api('POST', 'git/refs', {'ref': 'refs/heads/badges', 'sha': commit['sha']})
    print('Published tests and coverage metrics for '+source)


if __name__ == '__main__':
    main()
