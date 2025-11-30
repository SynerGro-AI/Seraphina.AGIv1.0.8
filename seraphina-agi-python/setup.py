from setuptools import setup, find_packages

setup(
    name="seraphina-agi-companion",
    version="0.1.0",
    description="Pure Python AGI Companion for Seraphina - No mining, no wallets",
    author="Seraphina AGI",
    packages=find_packages(),
    install_requires=[
        "requests",  # for HTTP
        "cryptography",  # for crypto
    ],
    entry_points={
        "console_scripts": [
            "seraphina-agi=seraphina_agi.run_agi:main",
        ],
    },
    python_requires=">=3.8",
)