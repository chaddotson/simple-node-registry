from __future__ import print_function
from argparse import ArgumentParser
from hashlib import sha1 as sha
from json import load, dump
from logging import basicConfig, getLogger, DEBUG, INFO
from os import error as oserror, makedirs
from os.path import basename, exists, join
from requests import get
from semver import max_satisfying
from time import sleep
from urllib import quote
from urllib2 import urlopen


logger = getLogger(__name__)

REPOSITORY_URL = 'https://registry.npmjs.org/'
BUF_SIZE = 65536
NICENESS = 0.1


PACKAGES_NPM_REQUIRES=[
    'number-is-nan', 'babel-runtime', 'babel-register', 'trim-right', 'babel-traverse', 'private', 'json5', 'globals',
    'to-fast-properties', 'babel-generator', 'babel-helpers', 'source-map-support', 'regenerator-runtime', 'home-or-tmp',
    'slash', 'invariant', 'babel-core', 'babylon', 'detect-indent', 'convert-source-map', 'esutils', 'core-js', 'jsesc',
    'js-tokens', 'babel-code-frame', 'loose-envify', 'babel-messages', 'ms', 'debug', 'is-finite', 'repeating', 'babel-types',
    'babel-template']


class PackageSpec(object):
    __slots__ = ['package_spec', 'is_scoped', 'scope', 'scoped_package_name', 'package_name', 'package_version']

    def __init__(self, package_spec):
        self.package_spec = package_spec
        self.is_scoped = False
        self.scope = None
        self.scoped_package_name = None
        self.package_name = None
        self.package_version = None
        self._process_spec()

    @property
    def registry_package_name(self):
        return self.scoped_package_name if self.is_scoped else self.package_name
        
    def _process_spec(self):
        self.is_scoped = self.package_spec.startswith('@')
        at_count = self.package_spec.count('@')

        if self.is_scoped:
            # scoped
            if at_count > 1:
                # version specified
                self.scoped_package_name, self.package_version = self.package_spec.rsplit('@', 1)
                self.scope, self.package_name = self.scoped_package_name[1:].rsplit('/')
            else:
                # version not specified
                self.scoped_package_name = self.package_spec
        else:
            # not scoped
            if at_count:
                # version specified
                self.package_name, self.package_version = self.package_spec.rsplit('@')
            else:
                # version not specified
                self.package_name = self.package_spec
    
    def __str__(self):
        return '{0}(package_spec={1.package_spec}, is_scoped={1.is_scoped}, scope={1.scope}, scoped_package_name={1.scoped_package_name}, package_name={1.package_name}, package_version={1.package_version}, registry_package_name={1.registry_package_name})'.format(self.__class__.__name__, self)


def get_package_info(package):
    url = join(REPOSITORY_URL, package.replace('/', '%2f'))
    logger.info("Getting info for %s from %s", package, url)

    content = get(url)
    return content.json()


def get_file_hash(path):
    tmphash = sha()

    with open(path, 'rb') as f:
        while True:
            data = f.read(BUF_SIZE)
            if not data:
                break
            tmphash.update(data)

    return tmphash.hexdigest()


def download_package(output_directory, spec, duplicate_download_preventer, force=False):
    """ Download the package specified into the output directory specified. """

    logger.info('Processing %s', spec)

    pkg_spec = PackageSpec(spec)

    info = get_package_info(pkg_spec.registry_package_name)

    # if no version was specified, use the latest specified.
    latest = str(info['dist-tags']['latest'])
    if pkg_spec.package_version is None:
        pkg_spec.package_version = latest

    # the python node-semver package doesn't work well with unicode, convert arguments to strings.
    pkg_spec.package_version = max_satisfying([str(v) for v in info['versions'].keys()], str(pkg_spec.package_version))

    if pkg_spec.registry_package_name in duplicate_download_preventer and pkg_spec.package_version in duplicate_download_preventer[pkg_spec.registry_package_name]:
        logger.info('Previously downloaded package: %s, version %s', pkg_spec.registry_package_name, pkg_spec.package_version)
        return
    
    # get information about the version the user wanted.
    version_info = info['versions'][pkg_spec.package_version]

    tarball_url = version_info['dist']['tarball']
    expected_shasum = version_info['dist']['shasum']


    # derive paths for storing the cached json info document and the tarball. Scoped packages are special.
    if pkg_spec.is_scoped:
        info_path = join(output_directory, 'scoped', pkg_spec.scope, pkg_spec.package_name) + '.json'
        tgz_directory = join(output_directory, 'scoped', pkg_spec.scope, 'tgz')
    else:
        info_path = join(output_directory, pkg_spec.package_name) + '.json'
        tgz_directory = join(output_directory, 'tgz')

    tgz_path = join(tgz_directory, basename(tarball_url))

    try:
        if not exists(tgz_directory):
            makedirs(tgz_directory)
    except oserror:
        logger.exception("Error creating output directory.")


    with open(info_path, 'w') as f:
        dump(info, f, indent=4)

    
    file_shasum = get_file_hash(tgz_path) if exists(tgz_path) else None
    
    # if the tarball exists and has a valid checksum, don't download a new copy.
    if (exists(tgz_path) and not force) and (file_shasum == expected_shasum):
        logger.info('Locally cached package: %s version: %s (latest: %s) at: %s', pkg_spec.registry_package_name, pkg_spec.package_version, latest, tarball_url)
    else:
        logger.info('Getting package: %s version: %s (latest: %s) at: %s', pkg_spec.registry_package_name, pkg_spec.package_version, latest, tarball_url)

        tarball = get(tarball_url)
        with open(tgz_path, 'wb') as f:
            f.write(tarball.content)

        file_shasum = get_file_hash(tgz_path) if exists(tgz_path) else None

        if not file_shasum == expected_shasum:
            logger.warning('''Package %s from %s downloaded by hash: %s doesn't match expected hash: %s''', pkg_spec.registry_package_name, tarball_url, file_shasum, expected_shasum)
    
    # to prevent circular dependency problems, track downloaded packages/versions.
    if pkg_spec.registry_package_name not in duplicate_download_preventer:
        duplicate_download_preventer[pkg_spec.registry_package_name] = set()
    duplicate_download_preventer[pkg_spec.registry_package_name].add(pkg_spec.package_version)    

    # cache all package dependencies and optoinal dependencies.
    logger.info('Processing dependencies: %s', pkg_spec.registry_package_name)
    for dependency, version in version_info.get('dependencies', {}).items():
        download_package(output_directory, dependency + '@' + version, duplicate_download_preventer, force)
    
    logger.info('Processing optional dependencies: %s', pkg_spec.registry_package_name)
    for dependency, version in version_info.get('dependencies', {}).items():
        download_package(output_directory, dependency + '@' + version, duplicate_download_preventer, force)
    
    logger.info('Done with package: %s', pkg_spec.registry_package_name)
    sleep(NICENESS)


def get_args():
    parser = ArgumentParser(description='Image Scraper')
    parser.add_argument('output_directory', help='Output file')
    parser.add_argument('packages', type=str, nargs='+', help='packages to cache (space seperated)')
    parser.add_argument('-p', '--package', help='packages argument is package.json formatted file.', default=False, action='store_true' )
    parser.add_argument('-v', '--verbose', help='Verbose log output', default=False, action='store_true')

    return parser.parse_args()

if __name__ == '__main__':
    basicConfig(level=INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    args = get_args()
    if args.verbose:
        getLogger('').setLevel(DEBUG)

    # simple method for preventing circular dependencies.  I don't know if that is
    # possible but I seem to have hit something like it.
    duplicate_download_preventer = dict()

    # if -p is specified, that means that instead of a list of packages via the command line,
    # a package.json format file has been specified.  We want to cache everything about it.
    packages = []
    if args.package:
        with open(args.packages[0], 'r') as f:
            info = load(f)
            packages += [dependency + '@' + version for dependency, version in info.get('devDependencies', {}).items()]
            packages += [dependency + '@' + version for dependency, version in info.get('dependencies', {}).items()]
            packages += [dependency + '@' + version for dependency, version in info.get('optionalDependencies', {}).items()]
    else:
        packages = args.packages

    for package in PACKAGES_NPM_REQUIRES + packages:
        download_package(args.output_directory, package, duplicate_download_preventer)

    logger.info('Downloaded %d packages total.', sum(len(s) for s in duplicate_download_preventer.values()))

