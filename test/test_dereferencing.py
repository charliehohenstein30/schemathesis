import pytest
import yaml

import schemathesis
from schemathesis.models import Endpoint

from .utils import as_param, get_schema, integer


@pytest.fixture()
def petstore():
    return get_schema("petstore_v2.yaml")


@pytest.mark.parametrize(
    "ref, expected",
    (
        (
            {"$ref": "#/definitions/Category"},
            {
                "properties": {"id": {"format": "int64", "type": "integer"}, "name": {"type": "string"}},
                "type": "object",
                "xml": {"name": "Category"},
            },
        ),
        (
            {"$ref": "#/definitions/Pet"},
            {
                "properties": {
                    "category": {
                        "properties": {"id": {"format": "int64", "type": "integer"}, "name": {"type": "string"}},
                        "type": "object",
                        "xml": {"name": "Category"},
                    },
                    "id": {"format": "int64", "type": "integer"},
                    "name": {"example": "doggie", "type": "string"},
                    "photoUrls": {
                        "items": {"type": "string"},
                        "type": "array",
                        "xml": {"name": "photoUrl", "wrapped": True},
                    },
                    "status": {
                        "description": "pet status in the store",
                        "enum": ["available", "pending", "sold"],
                        "type": "string",
                    },
                    "tags": {
                        "items": {
                            "properties": {"id": {"format": "int64", "type": "integer"}, "name": {"type": "string"}},
                            "type": "object",
                            "xml": {"name": "Tag"},
                        },
                        "type": "array",
                        "xml": {"name": "tag", "wrapped": True},
                    },
                },
                "required": ["name", "photoUrls"],
                "type": "object",
                "xml": {"name": "Pet"},
            },
        ),
    ),
)
def test_resolve(petstore, ref, expected):
    assert petstore.resolve(ref) == expected


def test_simple_dereference(testdir):
    # When a given parameter contains a JSON reference
    testdir.make_test(
        """
@schema.parametrize(method="POST")
@settings(max_examples=1)
def test_(request, case):
    request.config.HYPOTHESIS_CASES += 1
    assert case.path == "/v1/users"
    assert case.method == "POST"
    assert_int(case.body)
""",
        paths={
            "/users": {
                "post": {
                    "parameters": [
                        {
                            "schema": {"$ref": "#/definitions/SimpleIntRef"},
                            "in": "body",
                            "name": "object",
                            "required": True,
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
        definitions={"SimpleIntRef": {"type": "integer"}},
    )
    # Then it should be correctly resolved and used in the generated case
    result = testdir.runpytest("-v", "-s")
    result.assert_outcomes(passed=1)
    result.stdout.re_match_lines([r"Hypothesis calls: 1$"])


def test_recursive_dereference(testdir):
    # When a given parameter contains a JSON reference, that reference an object with another reference
    testdir.make_test(
        """
@schema.parametrize(method="POST")
@settings(max_examples=1)
def test_(request, case):
    request.config.HYPOTHESIS_CASES += 1
    assert case.path == "/v1/users"
    assert case.method == "POST"
    assert_int(case.body["id"])
""",
        paths={
            "/users": {
                "post": {
                    "parameters": [
                        {
                            "schema": {"$ref": "#/definitions/ObjectRef"},
                            "in": "body",
                            "name": "object",
                            "required": True,
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
        definitions={
            "ObjectRef": {
                "required": ["id"],
                "type": "object",
                "additionalProperties": False,
                "properties": {"id": {"$ref": "#/definitions/SimpleIntRef"}},
            },
            "SimpleIntRef": {"type": "integer"},
        },
    )
    # Then it should be correctly resolved and used in the generated case
    result = testdir.runpytest("-v", "-s")
    result.assert_outcomes(passed=1)
    result.stdout.re_match_lines([r"Hypothesis calls: 1$"])


def test_inner_dereference(testdir):
    # When a given parameter contains a JSON reference inside a property of an object
    testdir.make_test(
        """
@schema.parametrize(method="POST")
@settings(max_examples=1)
def test_(request, case):
    request.config.HYPOTHESIS_CASES += 1
    assert case.path == "/v1/users"
    assert case.method == "POST"
    assert_int(case.body["id"])
""",
        paths={
            "/users": {
                "post": {
                    "parameters": [
                        {
                            "schema": {
                                "type": "object",
                                "required": ["id"],
                                "properties": {"id": {"$ref": "#/definitions/SimpleIntRef"}},
                            },
                            "in": "body",
                            "name": "object",
                            "required": True,
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
        definitions={"SimpleIntRef": {"type": "integer"}},
    )
    # Then it should be correctly resolved and used in the generated case
    result = testdir.runpytest("-v", "-s")
    result.assert_outcomes(passed=1)
    result.stdout.re_match_lines([r"Hypothesis calls: 1$"])


def test_inner_dereference_with_lists(testdir):
    # When a given parameter contains a JSON reference inside a list in `allOf`
    testdir.make_test(
        """
@schema.parametrize(method="POST")
@settings(max_examples=1)
def test_(request, case):
    request.config.HYPOTHESIS_CASES += 1
    assert case.path == "/v1/users"
    assert case.method == "POST"
    assert_int(case.body["id"]["a"])
    assert_str(case.body["id"]["b"])
""",
        paths={
            "/users": {
                "post": {
                    "parameters": [
                        {
                            "schema": {
                                "type": "object",
                                "required": ["id"],
                                "properties": {
                                    "id": {"allOf": [{"$ref": "#/definitions/A"}, {"$ref": "#/definitions/B"}]}
                                },
                            },
                            "in": "body",
                            "name": "object",
                            "required": True,
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
        definitions={
            "A": {"type": "object", "required": ["a"], "properties": {"a": {"type": "integer"}}},
            "B": {"type": "object", "required": ["b"], "properties": {"b": {"type": "string"}}},
        },
    )
    # Then it should be correctly resolved and used in the generated case
    result = testdir.runpytest("-v", "-s")
    result.assert_outcomes(passed=1)
    result.stdout.re_match_lines([r"Hypothesis calls: 1$"])


def make_nullable_test_data(spec_version):
    field_name = {"openapi": "nullable", "swagger": "x-nullable"}[spec_version]
    return (
        (
            {
                "properties": {
                    "id": {"format": "int64", "type": "integer", field_name: True},
                    "name": {"type": "string"},
                },
                "type": "object",
            },
            {
                "properties": {
                    "id": {"anyOf": [{"format": "int64", "type": "integer"}, {"type": "null"}]},
                    "name": {"type": "string"},
                },
                "type": "object",
            },
        ),
        (
            {
                "parameters": [
                    {"name": "id", "in": "query", "type": "integer", "format": "int64", field_name: True},
                    {"name": "name", "type": "string"},
                ]
            },
            {
                "parameters": [
                    {"name": "id", "in": "query", "format": "int64", "anyOf": [{"type": "integer"}, {"type": "null"}]},
                    {"name": "name", "type": "string"},
                ]
            },
        ),
        (
            {
                "properties": {
                    "id": {"type": "string", "enum": ["a", "b"], field_name: True},
                    "name": {"type": "string"},
                },
                "type": "object",
            },
            {
                "properties": {
                    "id": {"anyOf": [{"type": "string", "enum": ["a", "b"]}, {"type": "null"}]},
                    "name": {"type": "string"},
                },
                "type": "object",
            },
        ),
    )


@pytest.mark.parametrize("nullable, expected", make_nullable_test_data("swagger"))
def test_x_nullable(petstore, nullable, expected):
    assert petstore.resolve(nullable) == expected


@pytest.mark.parametrize("nullable, expected", make_nullable_test_data("openapi"))
def test_nullable(openapi_30, nullable, expected):
    assert openapi_30.resolve(nullable) == expected


def test_nullable_parameters(testdir):
    testdir.make_test(
        """
@schema.parametrize()
@settings(max_examples=1)
def test_(request, case):
    request.config.HYPOTHESIS_CASES += 1
    assert case.path == "/v1/users"
    assert case.method == "GET"
    assert case.query["id"] is None
""",
        **as_param(integer(name="id", required=True, **{"x-nullable": True})),
    )
    # Then it should be correctly resolved and used in the generated case
    result = testdir.runpytest("-v", "-s")
    result.assert_outcomes(passed=1)
    result.stdout.re_match_lines([r"Hypothesis calls: 1$"])


def test_nullable_properties(testdir):
    testdir.make_test(
        """
@schema.parametrize(method="POST")
@settings(max_examples=1)
def test_(request, case):
    request.config.HYPOTHESIS_CASES += 1
    assert case.path == "/v1/users"
    assert case.method == "POST"
    assert case.body["id"] is None
""",
        paths={
            "/users": {
                "post": {
                    "parameters": [
                        {
                            "in": "body",
                            "name": "attributes",
                            "schema": {
                                "type": "object",
                                "properties": {"id": {"type": "integer", "format": "int64", "x-nullable": True}},
                                "required": ["id"],
                            },
                            "required": True,
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    )
    # Then it should be correctly resolved and used in the generated case
    result = testdir.runpytest("-vv", "-s")
    result.assert_outcomes(passed=1)
    result.stdout.re_match_lines([r"Hypothesis calls: 1$"])


def test_nullable_ref(testdir):
    testdir.make_test(
        """
@schema.parametrize(method="POST")
@settings(max_examples=1)
def test_(request, case):
    request.config.HYPOTHESIS_CASES += 1
    assert case.path == "/v1/users"
    assert case.method == "POST"
    assert case.body is None
""",
        paths={
            "/users": {
                "post": {
                    "parameters": [
                        {
                            "in": "body",
                            "name": "attributes",
                            "schema": {"$ref": "#/definitions/NullableIntRef"},
                            "required": True,
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
        definitions={"NullableIntRef": {"type": "integer", "x-nullable": True}},
    )
    # Then it should be correctly resolved and used in the generated case
    result = testdir.runpytest("-v", "-s")
    result.assert_outcomes(passed=1)
    result.stdout.re_match_lines([r"Hypothesis calls: 1$"])


def test_path_ref(testdir):
    # When path is specified via `$ref`
    testdir.make_test(
        """
@schema.parametrize()
@settings(max_examples=1)
def test_(request, case):
    request.config.HYPOTHESIS_CASES += 1
    assert case.path == "/v1/users"
    assert isinstance(case.body, str)
""",
        paths={"/users": {"$ref": "#/x-paths/UsersPath"}},
        **{
            # custom extension `x-paths` to be compliant with the spec, otherwise there is no handy place
            # to put the referenced object
            "x-paths": {
                "UsersPath": {
                    "post": {
                        "parameters": [{"schema": {"type": "string"}, "in": "body", "name": "object", "required": True}]
                    }
                }
            }
        },
    )
    # Then it should be correctly resolved and used in the generated case
    result = testdir.runpytest("-v", "-s")
    result.assert_outcomes(passed=1)
    result.stdout.re_match_lines([r"Hypothesis calls: 1$"])


def test_nullable_enum(testdir):
    testdir.make_test(
        """
@schema.parametrize()
@settings(max_examples=1)
def test_(request, case):
    request.config.HYPOTHESIS_CASES += 1
    assert case.path == "/v1/users"
    assert case.method == "GET"
    assert case.query["id"] is None
""",
        **as_param(integer(name="id", required=True, enum=[1, 2], **{"x-nullable": True})),
    )
    # Then it should be correctly resolved and used in the generated case
    result = testdir.runpytest("-v", "-s")
    result.assert_outcomes(passed=1)
    result.stdout.re_match_lines([r"Hypothesis calls: 1$"])


ROOT_SCHEMA = {
    "openapi": "3.0.2",
    "info": {"title": "Example API", "description": "An API to test Schemathesis", "version": "1.0.0"},
    "paths": {"/teapot": {"$ref": "paths/teapot.yaml#/TeapotCreatePath"}},
}
TEAPOT_PATHS = {
    "TeapotCreatePath": {
        "post": {
            "summary": "Test",
            "requestBody": {
                "description": "Test.",
                "content": {
                    "application/json": {"schema": {"$ref": "../schemas/teapot/create.yaml#/TeapotCreateRequest"}}
                },
                "required": True,
            },
            "responses": {"default": {"$ref": "../../common/responses.yaml#/DefaultError"}},
            "tags": ["ancillaries"],
        }
    }
}
TEAPOT_CREATE_SCHEMAS = {
    "TeapotCreateRequest": {
        "type": "object",
        "description": "Test",
        "additionalProperties": False,
        "properties": {"username": {"type": "string"}, "profile": {"$ref": "#/Profile"}},
        "required": ["username", "profile"],
    },
    "Profile": {
        "type": "object",
        "description": "Test",
        "additionalProperties": False,
        "properties": {"id": {"type": "integer"}},
        "required": ["id"],
    },
}
COMMON_RESPONSES = {
    "DefaultError": {
        "description": "Probably an error",
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"key": {"type": "string"}},
                    "required": ["key"],
                }
            }
        },
    }
}


def test_complex_dereference(testdir):
    # This tests includes:
    #   - references to other files
    #   - local references in referenced files
    #   - different directories - relative paths to other files
    schema_root = testdir.mkdir("root")
    common = testdir.mkdir("common")
    paths = schema_root.mkdir("paths")
    schemas = schema_root.mkdir("schemas")
    teapot_schemas = schemas.mkdir("teapot")
    root = schema_root / "root.yaml"
    root.write_text(yaml.dump(ROOT_SCHEMA), "utf8")
    (paths / "teapot.yaml").write_text(yaml.dump(TEAPOT_PATHS), "utf8")
    (teapot_schemas / "create.yaml").write_text(yaml.dump(TEAPOT_CREATE_SCHEMAS), "utf8")
    (common / "responses.yaml").write_text(yaml.dump(COMMON_RESPONSES), "utf8")
    schema = schemathesis.from_path(str(root))
    assert schema.endpoints["/teapot"]["POST"] == Endpoint(
        path="/teapot",
        method="POST",
        definition={
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {
                            "additionalProperties": False,
                            "description": "Test",
                            "properties": {
                                "profile": {
                                    "additionalProperties": False,
                                    "description": "Test",
                                    "properties": {"id": {"type": "integer"}},
                                    "required": ["id"],
                                    "type": "object",
                                },
                                "username": {"type": "string"},
                            },
                            "required": ["username", "profile"],
                            "type": "object",
                        }
                    }
                },
                "description": "Test.",
                "required": True,
            },
            "responses": {
                "default": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "additionalProperties": False,
                                "properties": {"key": {"type": "string"}},
                                "required": ["key"],
                                "type": "object",
                            }
                        }
                    },
                    "description": "Probably an error",
                }
            },
            "summary": "Test",
            "tags": ["ancillaries"],
        },
        body={
            "additionalProperties": False,
            "description": "Test",
            "properties": {
                "profile": {
                    "additionalProperties": False,
                    "description": "Test",
                    "properties": {"id": {"type": "integer"}},
                    "required": ["id"],
                    "type": "object",
                },
                "username": {"type": "string"},
            },
            "required": ["username", "profile"],
            "type": "object",
        },
        schema=schema,
    )
