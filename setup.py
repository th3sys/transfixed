from setuptools import setup, find_packages
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='cqgfixtrader',
    version='1.0.0',
    description='CQG FIX TRADER',
    long_description=long_description,
    url='https://github.com/th3sys/cqgfixtrader',
    author='Alexy Shelest',
    author_email='alexy@th3sys.com',
    license='MIT',
    platforms=['any'],
    classifiers=[
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.6'
    ],

    keywords='cqg fix protocol trading',

    packages=find_packages(exclude=['contrib', 'cqgfixtrader.egg-info', 'tests']),

    install_requires=['quickfix'],

    package_data={
        'cqgfixtrader': ['FIX42.xml', 'sample_config.ini'],
    },
)
