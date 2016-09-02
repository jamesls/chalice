import pytest
from pytest import fixture

import botocore.session
from botocore.stub import Stubber

from chalice.awsclient import TypedAWSClient


class StubbedSession(botocore.session.Session):
    def __init__(self, *args, **kwargs):
        super(StubbedSession, self).__init__(*args, **kwargs)
        self._cached_clients = {}
        self._client_stubs = {}

    def create_client(self, service_name, *args, **kwargs):
        if service_name not in self._cached_clients:
            client = self._create_stubbed_client(service_name, *args, **kwargs)
            self._cached_clients[service_name] = client
        return self._cached_clients[service_name]

    def _create_stubbed_client(self, service_name, *args, **kwargs):
        client = super(StubbedSession, self).create_client(
            service_name, *args, **kwargs)
        stubber = StubBuilder(Stubber(client))
        self._client_stubs[service_name] = stubber
        return client

    def stub(self, service_name):
        if service_name not in self._client_stubs:
            self.create_client(service_name)
        return self._client_stubs[service_name]

    def activate_stubs(self):
        for stub in self._client_stubs.values():
            stub.activate()

    def verify_stubs(self):
        for stub in self._client_stubs.values():
            stub.assert_no_pending_responses()


class StubBuilder(object):
    def __init__(self, stub):
        self.stub = stub
        self.activated = False
        self.pending_args = {}

    def __getattr__(self, name):
        if self.activated:
            # I want to be strict here to guide common test behavior.
            # This helps encourage the "record" "replay" "verify"
            # idiom in traditional mock frameworks.
            raise RuntimeError("Stub has already been activated: %s, "
                               "you must set up your stub calls before "
                               "calling .activate()" % self.stub)
        if not name.startswith('_'):
            # Assume it's an API call.
            self.pending_args['operation_name'] = name
            return self

    def assert_no_pending_responses(self):
        self.stub.assert_no_pending_responses()

    def activate(self):
        self.activated = True
        self.stub.activate()

    def returns(self, response):
        self.pending_args['service_response'] = response
        # returns() is essentially our "build()" method and triggers
        # creations of a stub response creation.
        p = self.pending_args
        self.stub.add_response(p['operation_name'],
                               expected_params=p['expected_params'],
                               service_response=p['service_response'])
        # And reset the pending_args for the next stub creation.
        self.pending_args = {}

    def raises_error(self, error_code, message):
        p = self.pending_args
        self.stub.add_client_error(p['operation_name'],
                                   service_error_code=error_code,
                                   service_message=message)
        # Reset pending args for next expectation.
        self.pending_args = {}

    def __call__(self, **kwargs):
        self.pending_args['expected_params'] = kwargs
        return self


@fixture
def stubbed_session():
    s = StubbedSession()
    return s


@fixture(autouse=True)
def set_region(monkeypatch):
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-west-2')
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'foo')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'bar')
    monkeypatch.delenv('AWS_PROFILE')
    # Ensure that the existing ~/.aws/{config,credentials} file
    # don't influence test results.
    monkeypatch.setenv('AWS_CONFIG_FILE', '/tmp/asdfasdfaf/does/not/exist')
    monkeypatch.setenv('AWS_SHARED_CREDENTIALS_FILE',
                       '/tmp/asdfasdfaf/does/not/exist2')


def test_can_query_lambda_function_exists(stubbed_session):
    stubbed_session.stub('lambda').get_function(FunctionName='myappname')\
            .returns({'Code': {}, 'Configuration': {}})

    stubbed_session.activate_stubs()

    awsclient = TypedAWSClient(stubbed_session)
    assert awsclient.lambda_function_exists(name='myappname')

    stubbed_session.verify_stubs()


def test_can_query_lambda_function_does_not_exist(stubbed_session):
    stubbed_session.stub('lambda').get_function(FunctionName='myappname')\
            .raises_error(error_code='ResourceNotFoundException',
                          message='ResourceNotFound')

    stubbed_session.activate_stubs()

    awsclient = TypedAWSClient(stubbed_session)
    assert not awsclient.lambda_function_exists(name='myappname')

    stubbed_session.verify_stubs()


def test_lambda_function_bad_error_propagates(stubbed_session):
    stubbed_session.stub('lambda').get_function(FunctionName='myappname')\
            .raises_error(error_code='UnexpectedError',
                          message='Unknown')

    stubbed_session.activate_stubs()

    awsclient = TypedAWSClient(stubbed_session)
    with pytest.raises(botocore.exceptions.ClientError):
        awsclient.lambda_function_exists(name='myappname')

    stubbed_session.verify_stubs()


def test_rest_api_exists(stubbed_session):
    desired_name = 'myappname'
    stubbed_session.stub('apigateway').get_rest_apis()\
        .returns(
            {'items': [
                {'createdDate': 1, 'id': 'wrongid1', 'name': 'wrong1'},
                {'createdDate': 2, 'id': 'correct', 'name': desired_name},
                {'createdDate': 3, 'id': 'wrongid3', 'name': 'wrong3'},
            ]})
    stubbed_session.activate_stubs()
    awsclient = TypedAWSClient(stubbed_session)
    assert awsclient.get_rest_api_id(desired_name) == 'correct'
    stubbed_session.verify_stubs()


def test_rest_api_does_not_exist(stubbed_session):
    stubbed_session.stub('apigateway').get_rest_apis()\
        .returns(
            {'items': [
                {'createdDate': 1, 'id': 'wrongid1', 'name': 'wrong1'},
                {'createdDate': 2, 'id': 'wrongid1', 'name': 'wrong2'},
                {'createdDate': 3, 'id': 'wrongid3', 'name': 'wrong3'},
            ]})
    stubbed_session.activate_stubs()
    awsclient = TypedAWSClient(stubbed_session)
    assert awsclient.get_rest_api_id('myappname') is None
    stubbed_session.verify_stubs()
