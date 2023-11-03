# API

The Zou API is REST-based. If you are looking for a Python client, see [Gazu](https://github.com/cgwire/gazu).

## Authentication

Before you can use any of the endpoints outline below, you will have to get a JWT to authorize your requests.

You can get a authorization token using a (form-encoded) POST request to `/auth/login`. With
`curl` this would look something like `curl -X POST <server_address>/auth/login -d "email=<youremail>&password=<yourpassword>`.

The response is a JSON object, specifically you'll need to provide the `access_token` for your future requests. 
 
Here is a complete authentication process as an example (again using `curl`):

    $ curl -X POST <server_address>/api/auth/login -d "email=<youremail>&password=<yourpassword>
    {"login": true", "access_token": "eyJ0e...", ...}
    
    $ jwt=eyJ0e...  # Store the access token for easier use
    
    $ curl -H "Authorization: Bearer $jwt" <server_address>/api/data/projects
    [{...},
     {...}]

## HTTP routes

The full specification of the API is available at the OpenAPI format here:

[https://api-docs.kitsu.cloud](https://api-docs.kitsu.cloud)


## Available data

Data you can store and retrieve are listed in the specification:
[Models specification](https://api-docs.kitsu.cloud/#model- Common fields for all model instances)
