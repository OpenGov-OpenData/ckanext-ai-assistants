import pytest
import mock
import responses
import string

from ckan.plugins import toolkit as tk
from ckan.tests import helpers, factories

from lib import jobs
from tests.helpers import FunctionalRQTestBase


def _add_responses_solr_passthru():
    responses.add_passthru(tk.config.get('solr_url'))
    responses.add_passthru('https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken')


@pytest.mark.usefixtures('clean_db', 'with_plugins', 'with_test_worker')
@pytest.mark.ckan_config('ckan.plugins', 'dq_assistant datastore xloader')
@pytest.mark.ckan_config('ckan.openapi.prompt_file', './prompts/test.yaml')
@pytest.mark.ckan_config('ckan.dq_assistant.redis_url', 'redis://redis:6379/3')
@pytest.mark.ckan_config('ckan.openapi.api_key', 'it-is-openapi-token')
class TestAction:

    @responses.activate
    def test_get_report_forbidden(self, app):
        _add_responses_solr_passthru()
        org = factories.Organization()
        user = factories.User()
        env = {"REMOTE_USER": user['name'].encode('ascii')}
        dataset = factories.Dataset(owner_org=org['id'])
        res = factories.Resource(user=user, format='csv', package_id=dataset['id'])
        resp = app.get(f'/dq_assistant/report/{res.get("package_id")}/resource/{res.get("id")}', extra_environ=env)
        assert resp.status_code == 403
        assert 'Check with AI' not in resp
        assert 'dq-assistant-btn' not in resp

    @responses.activate
    def test_get_report(self, app):
        _add_responses_solr_passthru()
        user = factories.Sysadmin()
        org = factories.Organization()
        env = {"REMOTE_USER": user['name'].encode('ascii')}
        dataset = factories.Dataset(owner_org=org['id'])
        res = factories.Resource(user=user, format='csv', package_id=dataset['id'])

        helpers.call_action(
            "xloader_submit",
            context=dict(user=user["name"]),
            resource_id=res["id"],
        )
        jobs.Worker().work(burst=True)

        response = app.get(f'/dq_assistant/report/{res.get("package_id")}/resource/{res.get("id")}', extra_environ=env)

        assert 200 == response.status_code
        assert 'Check with AI' in response
        assert 'dq-assistant-btn' in response

    @responses.activate
    def test_generate_report_without_xloader_task_status(self, app):
        responses.get('http://link.to.some.data/', body='line1 \n line2\n')
        _add_responses_solr_passthru()
        user = factories.Sysadmin()
        org = factories.Organization()
        env = {"REMOTE_USER": user['name'].encode('ascii')}
        dataset = factories.Dataset(owner_org=org['id'])
        res = factories.Resource(user=user, format='aaa', package_id=dataset['id'])

        with (mock.patch('ckanext.dq_assistant.client.send_to_ai', return_value='{}') as client):
            response = app.post(f'/dq_assistant/report/{res.get("package_id")}/resource/{res.get("id")}', extra_environ=env)

            assert 403 == response.status_code
            assert 'Check with AI' not in response
            assert 'dq-assistant-btn' not in response
            # assert 'dq-assistant-btn disabled' not in response.text
            assert client.call_count == 0

    @responses.activate
    def test_generate_report_for_private_resource(self, app):
        responses.get('http://link.to.some.data/', body='line1 \n line2\n')
        _add_responses_solr_passthru()
        user = factories.Sysadmin()
        org = factories.Organization()
        env = {"REMOTE_USER": user['name'].encode('ascii')}
        dataset = factories.Dataset(owner_org=org['id'])
        res = factories.Resource(user=user, format='csv', package_id=dataset['id'], private=True)

        with (mock.patch('ckanext.dq_assistant.client.send_to_ai', return_value='{}') as client):
            response = app.post(f'/dq_assistant/report/{res.get("package_id")}/resource/{res.get("id")}', extra_environ=env)

            assert 403 == response.status_code
            assert 'Check with AI' not in response
            assert 'dq-assistant-btn disabled' not in response
            assert client.call_count == 0


@pytest.mark.usefixtures('clean_db', 'with_plugins')
@pytest.mark.ckan_config('ckan.plugins', 'dq_assistant datastore xloader')
@pytest.mark.ckan_config('ckan.openapi.prompt_file', './prompts/test.yaml')
@pytest.mark.ckan_config('ckan.dq_assistant.redis_url', 'redis://redis:6379/3')
@pytest.mark.ckan_config('ckan.openapi.api_key', 'it-is-openapi-token')
class TestQA(FunctionalRQTestBase):

    @responses.activate
    def test_generate_report_with_xloader_task_status(self, app):
        responses.get('http://link.to.some.data/', body='column1\n value1; value2\n line2\n')
        _add_responses_solr_passthru()
        user = factories.Sysadmin()
        org = factories.Organization()
        env = {"REMOTE_USER": user['name'].encode('ascii')}
        dataset = factories.Dataset(owner_org=org['id'])
        res = factories.Resource(user=user, format='csv', package_id=dataset['id'])

        helpers.call_action(
            "xloader_submit",
            context=dict(user=user["name"]),
            resource_id=res["id"],
        )
        jobs.Worker().work(burst=True)

        with mock.patch('ckanext.dq_assistant.client.send_to_ai', return_value='{}') as client:
            url = tk.url_for('dq_assistant.resource_report', dataset_id=dataset["id"], resource_id=res.get("id"))
            post_response = app.post(url,
                                     extra_environ=env,
                                     follow_redirects=False)
            jobs.Worker().work(burst=True)
            assert 302 == post_response.status_code
            assert url in post_response.location

            get_response = app.get(url, extra_environ=env)
            assert 'Check with AI' not in get_response
            assert 'dq-assistant-btn' not in get_response
            assert client.call_count == 1

    @responses.activate
    def test_generate_report_with_file_longer_than_100_lines(self, app):
        file = 'column1\n value1\n value1\n {}'.format('\n'.join([' value1'] * 110))
        responses.get('http://link.to.some.data/', body=file)
        _add_responses_solr_passthru()
        user = factories.Sysadmin()
        org = factories.Organization()
        env = {"REMOTE_USER": user['name'].encode('ascii')}
        dataset = factories.Dataset(owner_org=org['id'])
        res = factories.Resource(user=user, format='csv', package_id=dataset['id'])

        helpers.call_action(
            "xloader_submit",
            context=dict(user=user["name"]),
            resource_id=res["id"],
        )
        jobs.Worker().work(burst=True)

        with mock.patch('ckanext.dq_assistant.client.send_to_ai', return_value='{}') as client:
            url = tk.url_for('dq_assistant.resource_report', dataset_id=dataset["id"], resource_id=res.get("id"))
            post_response = app.post(url,
                                     extra_environ=env,
                                     follow_redirects=False)
            jobs.Worker().work(burst=True)
            assert 302 == post_response.status_code
            assert url in post_response.location

            get_response = app.get(url, extra_environ=env)
            assert 'Check with AI' not in get_response
            assert 'dq-assistant-btn' not in get_response
            assert client.call_count == 1
            assert len(client.call_args[0][0]) == 100

    @responses.activate
    def test_generate_report_with_file_larger_than_5Mb(self, app):
        file = 'column1\n value1\n value1\n {}'.format('\n'.join([string.ascii_uppercase * 5000] * 105))
        responses.get('http://link.to.some.data/', body=file)
        _add_responses_solr_passthru()
        user = factories.Sysadmin()
        org = factories.Organization()
        env = {"REMOTE_USER": user['name'].encode('ascii')}
        dataset = factories.Dataset(owner_org=org['id'])
        res = factories.Resource(user=user, format='csv', package_id=dataset['id'])

        helpers.call_action(
            "xloader_submit",
            context=dict(user=user["name"]),
            resource_id=res["id"],
        )
        jobs.Worker().work(burst=True)

        with mock.patch('ckanext.dq_assistant.client.send_to_ai', return_value='{}') as client:
            url = tk.url_for('dq_assistant.resource_report', dataset_id=dataset["id"], resource_id=res.get("id"))
            post_response = app.post(url,
                                     extra_environ=env,
                                     follow_redirects=False)
            jobs.Worker().work(burst=True)
            assert 302 == post_response.status_code
            assert url in post_response.location

            get_response = app.get(url, extra_environ=env)
            assert 'Check with AI' not in get_response
            assert 'dq-assistant-btn' not in get_response
            assert client.call_count == 1
            assert len(client.call_args[0][0]) == 44
