# setup file to build the wheel

from setuptools import setup

setup(
    name='iris',
    version='0.0.4',
    description='InterSystems IRIS Embedded Python wrapper',
    author='grongier',
    package_dir={'': 'src'},
    packages=['iris'],
    python_requires='>=3.6',
)
