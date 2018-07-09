# simple-node-registry
Simple offline registry for helping with offline node installations.


## Installed
### Caching Files
usnr <cache_directory> -p <package.json>

usnr <cache_directory> <package@version> <package2@version> ...


### Serving Cached Files
snr <cache_directory>


## Standalone Scripts
### Caching Files
python downloader.py <cache_directory> -p <package.json>

python downloader.py <cache_directory> <package@version> <package2@version> ...


### Serving Cached Files
python server.py <cache_directory>


#### High Level Dependencies
Flask, node-semver, requests

#### All Dependencies (in installation order)
Werkzeug, click, MarkupSafe, Jinja2, itsdangerous, Flask, node-semver, idna, certifi, chardet, urllib3, requests


