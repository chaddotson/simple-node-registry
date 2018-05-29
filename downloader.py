
from __future__ import print_function
from argparse import ArgumentParser
from hashlib import sha1 as sha
from json import loads, dump
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

def get_package_info(package):
    url = join(REPOSITORY_URL, package.replace('/', '%2f'))
    logger.info("Getting info for %s from %s", package, url)

    content = get(url)
    return content.json()


from collections import namedtuple

class PackageSpec(object):
    __slots__ = [package_spec, is_scoped, scope, scoped_package_name, package_name, package_version]

    def __init__(spec):
        self.package_spec = package_spec
        self.package_spec = None
        self.is_scoped = False
        self.scope = None
        self.scoped_package_name = None
        self.package_name = None
        self.package_version = None
        self._process_spec()
        
    def _process_spec():
        self.is_scoped = self.package_spec.startswith('@')
        at_count = self.package_spec.count('@')

        if self.is_scoped:
            # scoped
            if at_count > 1:
                # scoped with version specified
                self.scoped_package_name, self.package_version = self.package_spec.rsplit('@')
                self.scope, self.package_name = self.scoped_package_name[1:].rsplit('/')
            else:
                # scoped with no version specified
                self.scoped_package_name = self.package_spec
        else:
            # not scoped
            if at_count:
                # version specified
                self.package_name, self.package_version = self.package_spec.rsplit('@')
            else:
                # version not specified
                self.package_name = self.package_spec

            




def get_package_name_and_version(package_spec):
    at_count = package_spec.count('@')

    if (package_spec.startswith('@') and at_count > 1) or (not package_spec.startswith('@') and at_count):
        package_components = package_spec.rsplit('@', 1)
    else:    
        package_components = [package_spec]

    return package_components[0], package_components[1] if len(package_components) > 1 else None




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
    name, version = get_package_name_and_version(spec)
    is_scoped = name.startswith('@')
    scope = name[1:].split('/')[0] if is_scoped else None
    non_scoped_name = name.split('/')[1] if is_scoped else None

    info = get_package_info(name)

    if is_scoped:
        print('=======================================================================================================================')
        print('=======================================================================================================================')
        print('=======================================================================================================================')
        print('=======================================================================================================================')
        print('=======================================================================================================================')
        print('=======================================================================================================================')
        print('=======================================================================================================================')

    latest = str(info['dist-tags']['latest'])
    if version is None:
        version = str(latest)

    version = max_satisfying([str(v) for v in info['versions'].keys()], str(version))

    if name in duplicate_download_preventer and version in duplicate_download_preventer[name]:
        logger.info('Previously downloaded package: %s, version %s', name, version)
        return
    
    version_info = info['versions'][version]

    tarball_url = version_info['dist']['tarball']
    expected_shasum = version_info['dist']['shasum']

    if is_scoped:
        info_path = join(output_directory, 'scoped', scope, non_scoped_name) + '.json'
        tgz_directory = join(output_directory, 'scoped', scope, 'tgz')
        
    else:
        info_path = join(output_directory, name) + '.json'
        tgz_directory = join(output_directory, 'tgz')

    tgz_path = join(tgz_directory, basename(tarball_url))

    try:
        if not exists(tgz_directory):
            makedirs(tgz_directory)
    except oserror:
        logger.exception("Error creating output directory.")

    file_shasum = get_file_hash(tgz_path) if exists(tgz_path) else None

    with open(info_path, 'w') as f:
        dump(info, f, indent=4)

    if (exists(tgz_path) and not force) and (file_shasum == expected_shasum):
        logger.info('Locally cached package: %s version: %s (latest: %s) at: %s', name, version, latest, tarball_url)
    else:
        logger.info('Getting package: %s version: %s (latest: %s) at: %s', name, version, latest, tarball_url)

        tarball = get(tarball_url)
        with open(tgz_path, 'wb') as f:
            f.write(tarball.content)

        file_shasum = get_file_hash(tgz_path) if exists(tgz_path) else None

        if not file_shasum == expected_shasum:
            logger.warning('''Package %s from %s downloaded by hash: %s doesn't match expected hash: %s''', name, tarball_url, file_shasum, expected_shasum)
    
    if name not in duplicate_download_preventer:
        duplicate_download_preventer[name] = set()

    duplicate_download_preventer[name].add(version)    

    logger.info('Processing dependencies')
    for dependency, version in version_info.get('dependencies', {}).items():
        download_package(output_directory, dependency + '@' + version, duplicate_download_preventer, force)
    
    sleep(0.1)


def get_args():
    parser = ArgumentParser(description='Image Scraper')
    parser.add_argument('output_directory', help='Output file')
    parser.add_argument('packages', type=str, nargs='+',  help='packages to cache (space seperated)')
    parser.add_argument('-v', '--verbose', help='Verbose log output', default=False, action='store_true')
    return parser.parse_args()

if __name__ == '__main__':
    basicConfig(level=INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    args = get_args()
    if args.verbose:
        getLogger('').setLevel(DEBUG)

    duplicate_download_preventer = dict()

    for package in args.packages:
        download_package(args.output_directory, package, duplicate_download_preventer)

    logger.info('Downloaded %d packages total.', sum(len(s) for s in duplicate_download_preventer.values()))

