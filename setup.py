from setuptools import setup, find_packages
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='transfixed',
    version='0.0.4',
    description='FIX TRADING LIBRARY',
    long_description=long_description,
    url='https://github.com/th3sys/transfixed',
    author='Alexy Shelest',
    author_email='alexy@th3sys.com',
    license='MIT',
    platforms=['any'],
    classifiers=[
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.6'
    ],

    keywords='gain capital futures cqg quickfix fix protocol trading',

    packages=find_packages(exclude=['transfixed.egg-info', 'test_gain']),

    install_requires=['quickfix', 'enum', 'future'],

    package_data={
        'transfixed': ['fix/FIX42.xml', 'fix/FIX44.xml', 'gain_config.ini', 'cqg_config.ini'],
    },
)
