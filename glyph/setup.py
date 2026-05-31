from setuptools import setup, find_packages

setup(
    name="seraphina-glyph",
    version="0.1.0",
    description="Glyph — Seraphina's package manager (parallel to pip).",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Seraphina Project",
    python_requires=">=3.11",
    packages=find_packages(exclude=("tests", "tests.*")),
    entry_points={
        "console_scripts": [
            "glyph = glyph.cli:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
)
