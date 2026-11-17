from setuptools import setup, find_packages

setup(
    name="samia",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "sqlparse>=0.4.4",
        "Faker>=20.0.0",
        "pydantic>=2.5.0",
        "click>=8.1.0",
        "PyYAML>=6.0.1",
        "rich>=13.7.0",
    ],
    entry_points={
        "console_scripts": [
            "samia = samia.cli:main",
        ],
    },
)
