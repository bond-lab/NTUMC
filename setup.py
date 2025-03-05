from setuptools import setup, find_packages

setup(
    name="ntumc-tagger",
    version="0.1.0",
    packages=find_packages(),
    description="WordNet tagging system for corpus annotation",
    author="NTU Multilingual Corpus Project",
    author_email="bond@ieee.org",
    python_requires=">=3.7",
    install_requires=[
        "sqlite3",
        "pyyaml",
        "tqdm",
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Programming Language :: Python :: 3",
        "Topic :: Text Processing :: Linguistic",
    ],
)
