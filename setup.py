import pathlib
import setuptools

here = pathlib.Path(__file__).parent
long_description = (here / "README.md").read_text(encoding="utf-8")
version_line = (here / "fast_bitrix24" / "__version__.py").read_text(encoding="utf-8")
__version__ = [
    line.split("=", 1)[1].strip().strip("'\"")
    for line in version_line.splitlines()
    if line.startswith("__version__")
][0]

requirements = [
    "aiohttp",
    "tqdm",
    "more_itertools",
    "icontract",
    "beartype>=0.22.9",
]

setuptools.setup(
    name="fast_bitrix24",
    version=__version__,
    author="Alexey Leshchenko",
    author_email="leshchenko@gmail.com",
    description=(
        "API wrapper для быстрого получения данных от Битрикс24 через "
        "REST API. Параллельные запросы к серверу, упаковка запросов "
        "в батчи, контроль скорости запросов, есть синхронный "
        "и асинхронный клиенты."
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/leshchenko1979/fast_bitrix24",
    packages=["fast_bitrix24"],
    exclude_package_data={
        "fast_bitrix24": ["test**"]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
    install_requires=requirements,
    license="MIT",
)
