from setuptools import find_packages, setup

setup(
    name='bearctl',
    version='0.1.0',
    packages=find_packages(include=['bearctl', 'bear.*']),
    setup_requires=['pytest-runner'],
    tests_require=['pytest'],
)
