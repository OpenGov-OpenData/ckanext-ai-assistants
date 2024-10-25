from setuptools import setup, find_packages
version = '0.1'

setup(
	name='ckanext-ai-assistants',
	version=version,
	description="Quick introduction to writiing CKAN extensions",
	long_description="""\
	""",
	classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
	keywords='',
	author='Peter Vorman',
	author_email='',
	url='http://ckan.org',
	license='GPL v3.0',
	packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
	namespace_packages=['ckanext', 'ckanext.dq_assistant'],
	include_package_data=True,
	zip_safe=False,
	install_requires=[
		'langchain',
		'langchain-openai',
		'openai-ratelimiter==0.7',
	],
	entry_points=\
	"""
        [ckan.plugins]
	dq_assistant=ckanext.dq_assistant.plugin:DQAIPlugin
	""",
)
