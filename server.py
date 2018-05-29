from __future__ import print_function
from flask import Flask, jsonify, send_from_directory
from json import load
from os.path import join
from utils import get_package_name_and_version

app = Flask(__name__)


# https://registry.npmjs.org/vue
# https://registry.npmjs.org/vue/-/vue-2.5.16.tgz

# https://registry.npmjs.org/@sindresorhus%2fis
# https://registry.npmjs.org/@sindresorhus/is/-/is-0.9.0.tgz



def load_json_info(path_to_json):
    # Q&D
    with open(path_to_json, 'r') as f:
        content = load(f)

    #local_url = "{0}/{1}".format(app.host, app.port)

    if u'versions' in content:
        for version in content['versions'].values():
            if u'dist' in version and u'tarball' in version['dist']:
                version['dist']['tarball']= version['dist']['tarball'].replace('https://registry.npmjs.org/', 'http://localhost:5000/')
    return content


@app.route('/<package>')
def get_package_info(package):

    path_to_json = join('./npm', package) + '.json'
    
    info = load_json_info(path_to_json)

    return jsonify(info)

@app.route('/@<string:scope>/<package>')
def get_scoped_package_info(scope, package):

    path_to_json = join('./npm', 'scoped', scope, package) + '.json'
    
    info = load_json_info(path_to_json)
    
    return jsonify(info)

@app.route('/<package>/-/<tarball>')
def get_package_tgz(package, tarball):
    path_to_tarballs = join('./npm', 'tgz')
    return send_from_directory(path_to_tarballs, tarball)

@app.route('/@<string:scope>/<package>/-/<tarball>')
def get_scoped_package_tgz(scope, package, tarball):
    path_to_tarballs = join('./npm', 'scoped', scope,  'tgz')

    return send_from_directory(path_to_tarballs, tarball)


