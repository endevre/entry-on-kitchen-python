from setuptools import setup, find_packages

setup(
    name='entry-on-kitchen',
    version='0.3.1',
    description='Official Python Module for using entry blocks on kitchen',
    author='Endevre Technologies',
    author_email='contact@endevre.com',
    packages=find_packages(),
    install_requires=['requests'],
    python_requires='>=3.7',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
    ],
)
