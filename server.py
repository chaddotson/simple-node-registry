from __future__ import print_function
from flask import Flask, jsonify, request, send_from_directory
from json import load
from logging.config import dictConfig
from os.path import join

app = Flask(__name__)


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
                version['dist']['tarball']= version['dist']['tarball'].replace('https://registry.npmjs.org/', 'http://localhost:5000/')
    return content


@app.route('/<string:package>')
def get_package_info(package):
    app.logger.info("Getting: %s", package)
    path_to_json = join('./npm', package) + '.json'
    info = load_json_info(path_to_json)
    return jsonify(info)


@app.route('/@<string:scope>/<string:package>')
def get_scoped_package_info(scope, package):
    app.logger.info("Getting: @%s/%s", scope, package)
    path_to_json = join('./npm', 'scoped', scope, package) + '.json'
    info = load_json_info(path_to_json)
    return jsonify(info)


@app.route('/<string:package>/-/<string:tarball>')
def get_package_tgz(package, tarball):
    path_to_tarballs = join('./npm', 'tgz')
    return send_from_directory(path_to_tarballs, tarball)


@app.route('/@<string:scope>/<string:package>/-/<string:tarball>')
def get_scoped_package_tgz(scope, package, tarball):
    path_to_tarballs = join('./npm', 'scoped', scope,  'tgz')

    return send_from_directory(path_to_tarballs, tarball)

def shutdown_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()


@app.route('/shutdown', methods=['POST'])
def shutdown():
    shutdown_server()
    return 'Server shutting down...'
