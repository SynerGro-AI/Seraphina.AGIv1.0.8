#!/usr/bin/env python3
"""
Glyph Language Engine v8.7 - Python Bridge
Justice & Mercy Anchor + 16D Binary/Float Hyper-Wheel

A sophisticated language engine that fuses Hebrew Gematria, binary processing,
and geometric transformations for deterministic, resonant code generation.
"""

from setuptools import setup, find_packages
import os

# Read the README file
def read_readme():
    readme_path = os.path.join(os.path.dirname(__file__), 'README.md')
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""

# Read requirements
def read_requirements():
    req_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    if os.path.exists(req_path):
        with open(req_path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    return []

setup(
    name="glyph-language-engine",
    version="8.7.0",
    author="Seraphina AGI",
    author_email="seraphina@agi.engine",
    description="Advanced language engine with Hebrew Gematria, binary processing, and geometric transformations",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/seraphina-agi/glyph-language-engine",
    packages=find_packages(),
    py_modules=['language_engine_bridge', 'dashboard_updates_v8_7'],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.8",
    install_requires=read_requirements(),
    extras_require={
        "wasm": ["wasmtime>=12.0.0"],
        "dev": [
            "pytest>=7.0.0",
            "black>=22.0.0",
            "mypy>=1.0.0",
        ],
        "dashboard": [
            "gradio>=4.0.0",
            "plotly>=5.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "glyph-engine=language_engine_bridge:main",
        ],
    },
    keywords="ai language-engine gematria cryptography geometry resonance",
    project_urls={
        "Bug Reports": "https://github.com/seraphina-agi/glyph-language-engine/issues",
        "Source": "https://github.com/seraphina-agi/glyph-language-engine",
        "Documentation": "https://github.com/seraphina-agi/glyph-language-engine#readme",
    },
)