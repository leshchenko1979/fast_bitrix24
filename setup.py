import setuptools

with open("README.md", "r", encoding='utf-8') as fh:
    long_description = fh.read()

setuptools.setup(
    name="fast_bitrix24",
    version="0.2.5",
    author="Alexey Leshchenko",
    author_email="leshchenko@gmail.com",
    description="A high-level Python SDK for Bitrix24 REST API aiming for speed of high volume transactions. Async operations, automatic batching and traffic throttling to prevent server rejections.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/leshchenko1979/lxutils",
    packages=['fast_bitrix24'],
    exclude_package_data={
        'fast_bitrix24': ["test**"]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
    install_requires=[
        'aiohttp',
        'asyncio',
        'tqdm',
        'more_itertools'
    ],
    license="MIT"
)