#!/usr/bin/env python3
# coding=utf-8

from setuptools import setup, find_packages

setup(name='python-ppapp',
    py_modules = ["pp_file3","pp_storage3","pp_app"],
    entry_points = {
        'console_scripts': ['ppapp=pp_app:run'],
    },
    author='gonewind.he',
      author_email='gonewind.he@gmail.com',
      maintainer='gonewind',
      maintainer_email='gonewind.he@gmail.com',
      url='https://github.com/gonewind73/pp_app',
      description='Linux/Windows  Virtual LAN application written in  python',
      long_description=open('README.rst',encoding='utf-8').read(),
      version='1.0.0',
      install_requires=['python-ppnetwork>=1.0.7',"PyYAML>=3.12" ,'python-ppvlan',"python-windutil"   ],
      python_requires='>=3',
      platforms=["Linux","Windows"],
      classifiers=[
          'Development Status :: 5 - Production/Stable',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: MIT License',
          'Programming Language :: Python :: 3',
          'Topic :: Software Development :: Libraries :: Python Modules',
          'Topic :: System :: Networking'])
