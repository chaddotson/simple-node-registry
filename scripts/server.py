from __future__ import print_function
from argparse import ArgumentParser
from flask import Flask, jsonify, request, send_from_directory
from json import load
from logging.config import dictConfig
from os.path import join
from socket import gethostname
from urllib import unquote

app = Flask(__name__)

# examples of non-scoped and scoped urls
# https://registry.npmjs.org/vue
# https://registry.npmjs.org/vue/-/vue-2.5.16.tgz

# https://registry.npmjs.org/@sindresorhus%2fis
# https://registry.npmjs.org/@sindresorhus/is/-/is-0.9.0.tgz

dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    }},
    'handlers': {'wsgi': {
        'class': 'logging.StreamHandler',
        'stream': 'ext://flask.logging.wsgi_errors_stream',
        'formatter': 'default'
    }},
    'root': {
        'level': 'INFO',
        'handlers': ['wsgi']
    }
})


def load_json_info(path_to_json):
    # Q&D
    with open(path_to_json, 'r') as f:
        content = load(f)

    if u'versions' in content:
        for version in content['versions'].values():
            if u'dist' in version and u'tarball' in version['dist']:
                version['dist']['tarball']= version['dist']['tarball'].replace('https://registry.npmjs.org/', app.config['NODE_URL'])
                version['dist']['tarball']= version['dist']['tarball'].replace('http://registry.npmjs.org/', app.config['NODE_URL'])
    return content


@app.route('/node/<string:package>')
def get_package_info(package):
    package = unquote(package)
    app.logger.info("Getting: %s", package)
    path_to_json = join(app.config['NODE_CACHE_DIRECTORY'], package) + '.json'
    info = load_json_info(path_to_json)
    return jsonify(info)


@app.route('/node/<string:scope>/<string:package>')
def get_scoped_package_info(scope, package):
    app.logger.info("Getting: @%s/%s", scope, package)
    path_to_json = join(app.config['NODE_CACHE_DIRECTORY'], scope, package) + '.json'
    info = load_json_info(path_to_json)
    return jsonify(info)


@app.route('/node/<string:package>/-/<string:tarball>')
def get_package_tgz(package, tarball):
    package = unquote(package)
    path_to_tarballs = join(app.config['NODE_CACHE_DIRECTORY'], 'tgz')
    app.logger.info('getting package %s from %s', package, path_to_tarballs)
    return send_from_directory(path_to_tarballs, tarball)


@app.route('/node/<string:scope>/<string:package>/-/<string:tarball>')
def get_scoped_package_tgz(scope, package, tarball):
    path_to_tarballs = join(app.config['NODE_CACHE_DIRECTORY'], scope,  'tgz')

    return send_from_directory(path_to_tarballs, tarball)


@app.route('/chromedriver/<path:path>')
def get_chromedriver_file(path):
    return send_from_directory(app.config['CHROMEDRIVER_CACHE_DIRECTORY'], path)


def shutdown_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()


@app.route('/shutdown', methods=['POST'])
def shutdown():
    shutdown_server()
    return 'Server shutting down...'


def get_args():
    parser = ArgumentParser(description='Offline Server (node, chromedriver, etc)')
    parser.add_argument('cache_directory', help='Cache directory')
    parser.add_argument('--host', help='Host', default='0.0.0.0', type=str)
    parser.add_argument('--port', help='Port', default=16000, type=int)
    parser.add_argument('-v', '--verbose', help='Verbose log output', default=False, action='store_true')
    return parser.parse_args()


def main():
    args = get_args()
    app.config['CACHE_DIRECTORY'] = args.cache_directory
    app.config['NODE_CACHE_DIRECTORY'] = join(args.cache_directory, 'node')
    app.config['CHROMEDRIVER_CACHE_DIRECTORY'] = join(args.cache_directory, 'chromedriver')
    app.config['HOST'] = args.host
    app.config['PORT'] = args.port
    app.config['NODE_URL'] = new_url = '{0}://{1}:{2}/node/'.format('http', app.config['HOST'], app.config['PORT'])
    app.config['CHROMEDRIVER_URL'] = new_url = '{0}://{1}:{2}/chromedriver/'.format('http', app.config['HOST'], app.config['PORT'])


    app.logger.info('Serving directory: %s', app.config['CACHE_DIRECTORY'])
    app.logger.info('Server url: %s', app.config['NODE_URL'])

    app.logger.info('\n\n***** NOTES *****\n* npm audit is not currently supported.\n* Add the following to a relevant .npmrc file.\n' \
                    '--------------------------------------\n' \
                    'registry=%s\naudit=false\n' \
                    '--------------------------------------\n\n' \
                    '* Add the following environment variable.\n' \
                    '--------------------------------------\n' \
                    'export CHROMEDRIVER_CDNURL=%s\n' \
                    '--------------------------------------\n',
                    app.config['NODE_URL'],
                    app.config['CHROMEDRIVER_URL'])

    #app.run(ssl_context='adhoc')
    app.run(
        debug=args.verbose,
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()

