import pytest
from pytest import fixture

from chalice.deployer import build_url_trie
from chalice.deployer import APIGatewayResourceCreator
from chalice.deployer import FULL_PASSTHROUGH, ERROR_MAPPING
from chalice.deployer import validate_configuration
from chalice.app import RouteEntry, ALL_ERRORS
from chalice.app import Chalice
from chalice.config import Config

from botocore.stub import Stubber
import botocore.session


_SESSION = None


class SimpleStub(object):
    def __init__(self, stubber):
        pass


@fixture
def stubbed_api_gateway():
    return stubbed_client('apigateway')


@fixture
def stubbed_lambda():
    return stubbed_client('lambda')


@fixture
def sample_app():
    app = Chalice('sample')

    @app.route('/')
    def foo():
        return {}

    return app


def stubbed_client(service_name):
    global _SESSION
    if _SESSION is None:
        _SESSION = botocore.session.get_session()
    client = _SESSION.create_client(service_name,
                                    region_name='us-west-2')
    stubber = Stubber(client)
    return client, stubber


def node(name, uri_path, children=None, resource_id=None,
      parent_resource_id=None, is_route=False):
    if children is None:
        children = {}
    return {
        'name': name,
        'uri_path': uri_path,
        'children': children,
        'resource_id': resource_id,
        'parent_resource_id': parent_resource_id,
        'is_route': is_route,
        'route_entry': None,
    }


n = node


def test_url_trie():
    assert build_url_trie({'/': None}) == n(name='', uri_path='/',
                                            is_route=True)


def test_single_nested_route():
    assert build_url_trie({'/foo/bar': None}) == n(
        name='', uri_path='/',
        children={
            'foo': n('foo', '/foo',
                     children={'bar':  n('bar', '/foo/bar', is_route=True)})
        }
    )


def test_multiple_routes():
    assert build_url_trie({'/foo/bar': None, '/bar': None, '/': None}) == n(
        name='', uri_path='/', is_route=True,
        children={
            'bar': n('bar', '/bar', is_route=True),
            'foo': n('foo', '/foo',
                     children={'bar':  n('bar', '/foo/bar', is_route=True)})
        }
    )


def test_multiple_routes_on_single_spine():
    assert build_url_trie({'/foo/bar': None, '/foo': None, '/': None}) == n(
        name='', uri_path='/', is_route=True,
        children={
            'foo': n('foo', '/foo', is_route=True,
                     children={'bar':  n('bar', '/foo/bar', is_route=True)})
        }
    )


def test_trailing_slash_routes_result_in_error():
    app = Chalice('appname')
    app.routes = {'/trailing-slash/': None}
    config = Config.create(chalice_app=app)
    with pytest.raises(ValueError):
        validate_configuration(config)


def test_manage_iam_role_false_requires_role_arn(sample_app):
    config = Config.create(chalice_app=sample_app, manage_iam_role=False,
                           iam_role_arn='arn:::foo')
    assert validate_configuration(config) is None


def test_validation_error_if_no_role_provided_when_manage_false(sample_app):
    # We're indicating that we should not be managing the
    # IAM role, but we're not giving a role ARN to use.
    # This is a validation error.
    config = Config.create(chalice_app=sample_app, manage_iam_role=False)
    with pytest.raises(ValueError):
        validate_configuration(config)


def add_expected_calls_to_map_error(error_cls, gateway_stub):
    gateway_stub.add_response(
        'put_integration_response',
        service_response={},
        expected_params={
            'httpMethod': 'POST',
            'resourceId': 'parent-id',
            'responseTemplates': {'application/json': ERROR_MAPPING},
            'restApiId': 'rest-api-id',
            'selectionPattern': '%s.*' % error_cls.__name__,
            'statusCode': str(error_cls.STATUS_CODE),
        }
    )
    gateway_stub.add_response(
        'put_method_response',
        service_response={},
        expected_params={
            'httpMethod': 'POST',
            'resourceId': 'parent-id',
            'responseModels': {
                'application/json': 'Empty',
            },
            'restApiId': 'rest-api-id',
            'statusCode': str(error_cls.STATUS_CODE),
        }
    )


def test_can_build_resource_routes_for_single_view(stubbed_api_gateway, stubbed_lambda):
    route_trie = {
        'name': '',
        'uri_path': '/',
        'children': {},
        'resource_id': 'parent-id',
        'parent_resource_id': None,
        'is_route': True,
        'route_entry': RouteEntry(None, 'index_view', '/', ['POST'],
                                  content_types=['application/json']),
    }
    gateway_client, gateway_stub = stubbed_api_gateway
    lambda_client, lambda_stub = stubbed_lambda
    random_id = lambda: "random-id"
    g = APIGatewayResourceCreator(gateway_client, lambda_client,
                                  'rest-api-id',
                                  'arn:aws:lambda:us-west-2:123:function:name',
                                  random_id_generator=random_id)

    gateway_stub.add_response(
        'put_method',
        service_response={},
        expected_params={
            'resourceId': 'parent-id',
            'authorizationType': 'NONE',
            'restApiId': 'rest-api-id',
            'httpMethod': 'POST',
        })
    gateway_stub.add_response(
        'put_integration',
        service_response={},
        expected_params={
            'httpMethod': 'POST',
            'integrationHttpMethod': 'POST',
            'passthroughBehavior': 'NEVER',
            'requestTemplates': {
                'application/json': FULL_PASSTHROUGH,
            },
            'resourceId': 'parent-id',
            'restApiId': 'rest-api-id',
            'type': 'AWS',
            'uri': ('arn:aws:apigateway:us-west-2:lambda:path'
                    '/2015-03-31/functions/arn:aws:lambda:us-west'
                    '-2:123:function:name/invocations')
        }
    )
    gateway_stub.add_response(
        'put_integration_response',
        service_response={},
        expected_params={
            'httpMethod': 'POST',
            'resourceId': 'parent-id',
            'responseTemplates': {
                'application/json': '',
            },
            'restApiId': 'rest-api-id',
            'statusCode': '200',
        }
    )
    gateway_stub.add_response(
        'put_method_response',
        service_response={},
        expected_params={
            'httpMethod': 'POST',
            'resourceId': 'parent-id',
            'responseModels': {
                'application/json': 'Empty',
            },
            'restApiId': 'rest-api-id',
            'statusCode': '200',
        }
    )
    for error_cls in ALL_ERRORS:
        add_expected_calls_to_map_error(error_cls, gateway_stub)
    lambda_stub.add_response(
        'add_permission',
        service_response={},
        expected_params={
            'Action': 'lambda:InvokeFunction',
            'FunctionName': 'name',
            'Principal': 'apigateway.amazonaws.com',
            'SourceArn': 'arn:aws:execute-api:us-west-2:123:rest-api-id/*',
            'StatementId': 'random-id',
        }
    )
    gateway_stub.activate()
    lambda_stub.activate()
    g.build_resources(route_trie)
