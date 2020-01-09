from setuptools import setup, find_packages

with open("README.md") as f:
    long_description = f.read()

setup(
    name="aio-krpc-server",
    version="0.0.7",
    description="Asyncio KRPC-server",
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=["Programming Language :: Python"],
    keywords="Async Kademlia RPC-server",
    author="D.Bashkirtsevich",
    author_email="bashkirtsevich@gmail.com",
    url="https://github.com/bashkirtsevich-llc/aiokrpc",
    license="GPL3 License",
    include_package_data=True,
    zip_safe=True,
    packages=find_packages("src"),
    package_dir={"": "src"},
    python_requires=">=3.6.*",
    install_requires=[
        "aio-udp-server==0.0.6",
        "Cerberus==1.3.1",
        "py3-bencode==0.0.3"
    ]
)
