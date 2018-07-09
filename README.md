# simple-node-registry
Simple offline cache for helping with offline node installations.


## Caching Files
python downloader.py <cache_directory> -p <package.json>

python downloader.py <cache_directory> <package@version> <package2@version> ...


## Serving Cached Files
python server.py <cache_directory>


