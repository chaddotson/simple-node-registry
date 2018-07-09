from os.path import dirname, join
from setuptools import setup

version = '0.2.0'

def read(fname):
    return open(join(dirname(__file__), fname)).read()

with open('requirements.txt', 'r') as f:
    install_reqs = f.readlines()

setup(name='simple_node_registry',
      version=version,
      author='Chad Dotson',
      author_email="chad@cdotson.com",
      description='Simple offline mirror for helping with offline node installations.',
      license="GNUv3",
      keywords=['node', 'registry', 'mirror', 'offline'],
      url="https://github.com/chaddotson/simple-node-registry/",
      packages=['scripts'],
      install_requires=install_reqs,
      include_package_data=True,
      entry_points={
          'console_scripts': [
              'usnr = scripts.downloader:main',
              'snr = scripts.server:main',
          ]
      },
      classifiers=[
          "Development Status :: 4 - Beta",
          "Topic :: Utilities",
          "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
      ]
)