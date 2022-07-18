from setuptools import find_packages, setup

setup(
    name="bearctl",
    version="0.1.0",
    packages=find_packages(include=["bear", "bear.*"]),
    # setup_requires=["pytest-runner"],
    # tests_require=["pytest"],
    intstall_requires=[
        "click",
        "dasbus",
        "pulsectl",
    ],
    entry_points={"console_scripts": ["bearctl=bear.main:main"]},
)
