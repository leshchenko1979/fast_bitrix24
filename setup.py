import setuptools

with open("README.md", "r", encoding='utf-8') as fh:
    long_description = fh.read()

with open('requirements.txt', 'r', encoding='utf-8') as fh:
    requirements = fh.read().splitlines()

setuptools.setup(
    name="fast_bitrix24",
    version="1.5.12",
    author="Alexey Leshchenko",
    author_email="leshchenko@gmail.com",
    description='API wrapper для быстрого получения данных от Битрикс24 через '
                'REST API. Параллельные запросы к серверу, упаковка запросов '
                'в батчи, контроль скорости запросов, есть синхронный '
                'и асинхронный клиенты.',
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
    install_requires=requirements,
    license="MIT"
)
