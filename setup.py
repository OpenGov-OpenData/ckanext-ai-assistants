from setuptools import setup, find_packages

version = '0.0.1'

setup(
    name='ckanext-ai-assistants',
    version=version,
    description="Quick introduction to writiing CKAN extensions",
    long_description="""""",
    license='AGPL',
    classifiers=[
        # How mature is this project? Common values are
        # 3 - Alpha
        # 4 - Beta
        # 5 - Production/Stable
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)',
        'Programming Language :: Python :: 3.9',
    ],
    keywords='ckan plugin',
    author='Peter Vorman',
    author_email='pvorman@opengov.com',
    url='http://ckan.org',
    packages=find_packages(exclude=['examples', 'tests']),
    namespace_packages=['ckanext'],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'redis',
        'langchain>=0.0.158',
        'langchain-openai==0.1.25',
        'tiktoken==0.8.0',
        'SQLAlchemy==1.3.24',
    ],
    entry_points="""
    [ckan.plugins]
    dq_assistant=ckanext.dq_assistant.plugin:DQAIPlugin
    """,
)
