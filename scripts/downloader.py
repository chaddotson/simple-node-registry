from __future__ import print_function
from argparse import ArgumentParser
from hashlib import sha1 as sha
from json import load, dump
from logging import basicConfig, getLogger, DEBUG, INFO
from os import error as oserror, makedirs
from os.path import basename, dirname, exists, join
from requests import get
from semver import max_satisfying, lte
from time import sleep
from urllib import quote
from urllib2 import urlopen
import xml.etree.ElementTree as ET


logger = getLogger(__name__)

REPOSITORY_URL = 'https://registry.npmjs.org/'
BUF_SIZE = 65536
NICENESS = 0.001


PACKAGES_NPM_REQUIRES=[
    'number-is-nan', 'babel-runtime', 'babel-register', 'trim-right', 'babel-traverse', 'private', 'json5', 'globals',
    'to-fast-properties', 'babel-generator', 'babel-helpers', 'source-map-support', 'regenerator-runtime', 'home-or-tmp',
    'slash', 'invariant', 'babel-core', 'babylon', 'detect-indent', 'convert-source-map', 'esutils', 'core-js', 'jsesc',
    'js-tokens', 'babel-code-frame', 'loose-envify', 'babel-messages', 'ms', 'debug', 'is-finite', 'repeating', 'babel-types',
    'babel-template', 'npm']


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

    def __eq__(self, other):
        # checking package spec is good enough since everything else is derived from it.
        return self.package_spec == other.package_spec


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
    content = get(url)
    logger.info("Getting info for %s from %s, status: %d", package, url, content.status_code)

    if content.status_code != 200:
        raise FailedToDownloadPackageInfoError()

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

        

class PackageVersionAlreadyRequiredError(RuntimeError):
    pass


class FailedToDownloadPackageInfoError(RuntimeError):
    pass


class Package(object):
    def __init__(self, pkg_name):
        self.pkg_name = pkg_name
        self.is_scoped = pkg_name.startswith('@')

        self.info = get_package_info(self.pkg_name)
        self.required_versions = set()

    @property
    def latest(self):
        return str(self.info['dist-tags']['latest']) if self.info is not None else None

    @property
    def next_version(self):
        return str(self.info['dist-tags']['next']) if 'next' in self.info['dist-tags'] else None


    def add_required_version(self, pkg_version):
        version_spec = pkg_version
        logger.debug('Initial version spec: %s', version_spec)

        if version_spec is None:
            logger.debug("Version not specified, using latest (%s)", self.latest)
            version_spec =  self.latest

        # the python node-semver package doesn't work well with unicode, convert arguments to strings.
        pkg_versions = [str(v) for v in  self.info['versions'].keys()]
        filtered_pkg_versions = [v for v in pkg_versions if lte(v, self.latest, False)]

        logger.debug('Finding version (%s) up to latest(%s)', version_spec, self.latest)

        download_version = max_satisfying(filtered_pkg_versions, str(version_spec))

        if download_version is None:
            logger.debug('Version (%s) not found up to latest < latest(%s) trying all.', version_spec, self.latest)
            download_version = max_satisfying(pkg_versions, str(version_spec))
        
        if download_version in self.required_versions:
            raise PackageVersionAlreadyRequiredError()
        
        self.required_versions.add(download_version)
        return self.info['versions'][download_version]
    

def determine_download_version(pkg_spec, package):
    version_spec = pkg_spec.package_version
    logger.info('Initial version spec: %s', version_spec)

    if version_spec is None:
        logger.info("Version not specified, using latest (%s)", package.latest)
        version_spec =  package.latest

    # the python node-semver package doesn't work well with unicode, convert arguments to strings.
    pkg_versions = [str(v) for v in  package.info['versions'].keys()]
    filtered_pkg_versions = [v for v in pkg_versions if lte(v, package.latest, False)]

    logger.info('Finding version (%s) up to latest(%s)', version_spec, package.latest)

    download_version = max_satisfying(filtered_pkg_versions, str(version_spec))

    if download_version is None:
        logger.info('Version (%s) not found up to latest < latest(%s) trying all.', version_spec, package.latest)
        download_version = max_satisfying(pkg_versions, str(version_spec))
    
    return download_version


def split_package_spec(spec):
    if spec.startswith('@'):
        return spec.rsplit('@', 1)  if spec.count('@') > 1 else (spec, None)
    else:
        return spec.rsplit('@', 1) if '@' in spec else (spec, None)
    

def crawl_package_info(packages, spec):
    """ Download the package specified into the output directory specified. """

    logger.debug('Processing %s', spec)

    pkg_name, pkg_version = split_package_spec(spec)

    if pkg_name not in packages:
        try:
            packages[pkg_name] = Package(pkg_name)
        except FailedToDownloadPackageInfoError:
            logger.exception('Failed to download packge info for: %s', pkg_name)
            return

    package = packages[pkg_name]
    
    try:
        version_info = package.add_required_version(pkg_version)
        
        # cache all package dependencies and optoinal dependencies.
        logger.debug('Processing dependencies: %s', pkg_name)
        for dependency, version in version_info.get('dependencies', {}).items():
            crawl_package_info(packages, dependency + '@' + version)
    
        logger.debug('Processing optional dependencies: %s', pkg_name)
        for dependency, version in version_info.get('dependencies', {}).items():
            crawl_package_info(packages, dependency + '@' + version)
        
    except PackageVersionAlreadyRequiredError:
        logger.debug('Package version already required - package: %s, version %s', pkg_name, pkg_version)
        pass

    logger.debug('Done with: %s', spec)
    sleep(NICENESS)


def download_chromedriver(output_directory):
    logger.info('Downloading chromedriver resources.')
    ns = {'ChromeDriver': 'http://doc.s3.amazonaws.com/2006-03-01'}

    r = get('http://chromedriver.storage.googleapis.com/')

    root = ET.fromstring(r.content)

    info_output_file = join(output_directory, 'chromedriver.xml')
    resource_base = output_directory

    try:
        makedirs(resource_base)
    except oserror:
        pass
        # logger.exception("Error creating output directory for chrome driver.")

    chromedriver_info = get('https://chromedriver.storage.googleapis.com/')

    with open(info_output_file, 'w') as f:
        print(chromedriver_info.content, file=f)
        
    for installable in root.findall('ChromeDriver:Contents', ns):
        element = installable.find('ChromeDriver:Key', ns)
        resource_url = join('https://chromedriver.storage.googleapis.com/', element.text)
        
        save_path = join(resource_base, element.text)
        try:
            makedirs(dirname(save_path))
        except oserror:
            pass
            # logger.exception("Error creating output directory for chrome driver version.")

        if exists(save_path):
            logger.info("Using cached %s at %s", resource_url, save_path)
            continue

        logger.info("Downloading %s to %s", resource_url, save_path)
        
        downloaded = get(resource_url)

        with open(save_path, 'wb') as f:
            f.write(downloaded.content)


def download_node_dependencies(output_directory_base, specified_packages):
    logger.info('Downloading node dependencies.')

    required_packages = {}
    for spec in packages:
        crawl_package_info(required_packages, spec)

    for package in required_packages.values():
        if package.is_scoped:
            scope, file_base = package.pkg_name.split('/', 1)
            output_directory = join(output_directory_base, scope)
        else:
            file_base = package.pkg_name
            output_directory = output_directory_base
                    
        info_path = join(output_directory, file_base) + '.json'
        tgz_directory = join(output_directory, 'tgz')

        try:
            if not exists(tgz_directory):
                makedirs(tgz_directory)
        except oserror:
            logger.exception("Error creating output directory.")

        with open(info_path, 'w') as f:
            dump(package.info, f, indent=4)

        for version in package.required_versions:
            tarball_url = package.info['versions'][version]['dist']['tarball']
            expected_shasum = package.info['versions'][version]['dist']['shasum']
            tgz_path = join(tgz_directory, basename(tarball_url))

            # print(package.pkg_name, version, tarball_url, expected_shasum)

            if exists(tgz_path) and get_file_hash(tgz_path) == expected_shasum:
                logger.info('Locally cached package: %s version: %s (latest: %s) at: %s', package.pkg_name, version, package.latest, tarball_url)
            else:
                logger.info('Getting package: %s version: %s (latest: %s) at: %s', package.pkg_name, version, package.latest, tarball_url)

                tarball = get(tarball_url)
                with open(tgz_path, 'wb') as f:
                    f.write(tarball.content)

                file_shasum = get_file_hash(tgz_path) if exists(tgz_path) else None

                if not file_shasum == expected_shasum:
                    logger.warning('''Package %s from %s downloaded by hash: %s doesn't match expected hash: %s''', package.pkg_name, tarball_url, file_shasum, expected_shasum)


def download_package(output_directory, spec, duplicate_download_preventer, force=False):
    """ Download the package specified into the output directory specified. """

    logger.info('Processing %s', spec)

    pkg_spec = PackageSpec(spec)

    info = get_package_info(pkg_spec.registry_package_name)

    # if no version was specified, use the latest specified.
    latest = str(info['dist-tags']['latest'])
    next_version = str(info['dist-tags']['next']) if 'next' in info['dist-tags'] else None

    version_spec = pkg_spec.package_version
    logger.info('Initial version spec: %s', version_spec)

    if version_spec is None:
        logger.info("Version not specified, using latest (%s)", latest)
        version_spec = latest

    # the python node-semver package doesn't work well with unicode, convert arguments to strings.
    pkg_versions = [str(v) for v in info['versions'].keys()]
    filtered_pkg_versions = [v for v in pkg_versions if lte(v, latest, False)]

    logger.info('Finding version (%s) up to latest(%s)', version_spec, latest)

    download_version = max_satisfying(filtered_pkg_versions, str(version_spec))

    if download_version is None:
        logger.info('Version (%s) not found up to latest < latest(%s) trying all.', version_spec, latest)
        download_version = max_satisfying(pkg_versions, str(version_spec))

    if pkg_spec.registry_package_name in duplicate_download_preventer and download_version in duplicate_download_preventer[pkg_spec.registry_package_name]:
        logger.info('Previously downloaded package: %s, version %s', pkg_spec.registry_package_name, download_version)
        return
    
    # get information about the version the user wanted.
    version_info = info['versions'][download_version]
    
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

    
    # file_shasum = get_file_hash(tgz_path) if exists(tgz_path) else None
    
    # if the tarball exists and has a valid checksum, don't download a new copy.
    # if (exists(tgz_path) and not force) and (file_shasum == expected_shasum):
    if exists(tgz_path) and not force:
        logger.info('Locally cached package: %s version: %s (latest: %s) at: %s', pkg_spec.registry_package_name, download_version, latest, tarball_url)
    else:
        logger.info('Getting package: %s version: %s (latest: %s) at: %s', pkg_spec.registry_package_name, download_version, latest, tarball_url)

        tarball = get(tarball_url)
        with open(tgz_path, 'wb') as f:
            f.write(tarball.content)

        file_shasum = get_file_hash(tgz_path) if exists(tgz_path) else None

        if not file_shasum == expected_shasum:
            logger.warning('''Package %s from %s downloaded by hash: %s doesn't match expected hash: %s''', pkg_spec.registry_package_name, tarball_url, file_shasum, expected_shasum)
    
    # to prevent circular dependency problems, track downloaded packages/versions.
    if pkg_spec.registry_package_name not in duplicate_download_preventer:
        duplicate_download_preventer[pkg_spec.registry_package_name] = set()
    duplicate_download_preventer[pkg_spec.registry_package_name].add(download_version)    

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
    parser.add_argument('--skip_chromedriver', help='Don\'t download chromedriver files.', default=False, action='store_true' )
    parser.add_argument('--skip_node', help='Don\'t download node dependencies.', default=False, action='store_true' )
    parser.add_argument('-p', '--package', help='packages argument is package.json formatted file.', default=False, action='store_true' )
    parser.add_argument('-n', '--noextras', help='don\'t include node extras (dependencies automatically gotten by node.', default=False, action='store_true' )
    parser.add_argument('-v', '--verbose', help='Verbose log output', default=False, action='store_true')

    return parser.parse_args()


def main():
    basicConfig(level=INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    args = get_args()
    if args.verbose:
        getLogger('').setLevel(DEBUG)

    if not args.skip_chromedriver:
        download_chromedriver(join(args.output_directory, 'chromedriver'))
    
    if not args.skip_node:
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

        packages = packages if args.noextras else PACKAGES_NPM_REQUIRES + packages

        download_node_dependencies(join(args.output_directory, 'node'), packages)


if __name__ == '__main__':
    main()