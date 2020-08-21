import setuptools

with open("README.md", "r", encoding='utf-8') as fh:
    long_description = fh.read()

setuptools.setup(
    name="fast_bitrix24",
    version="0.3.5",
    author="Alexey Leshchenko",
    author_email="leshchenko@gmail.com",
    description="Высокоуровневый API для Python 3.7+ для быстрого получения данных от Битрикс24 через REST API. Параллельные запросы к серверу, упаковка запросов в батчи, контроль скорости запросов.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/leshchenko1979/fast_bitrix24",
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
        'tqdm'
    ],
    license="MIT"
)