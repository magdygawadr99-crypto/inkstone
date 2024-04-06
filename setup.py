from setuptools import find_packages, setup

setup(
    name="inkstone",
    version="0.0.1",
    description="static site generator",
    packages=find_packages(exclude=["tests*"]),
    python_requires=">=3.10",
)
