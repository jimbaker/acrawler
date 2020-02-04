from setuptools import setup, find_packages
setup(
    name="acrawler",
    version="0.1",
    packages=find_packages(),
    scripts=["acrawl"],
    author="Jim Baker",
    author_email="jim.baker@python.org",
    description="Yet another async crawler",
    keywords="asyncio crawler",
    url="https://github.com/jimbaker/acrawler/",
    classifiers=[
        "License :: OSI Approved :: Apache Software License"
    ]
)
