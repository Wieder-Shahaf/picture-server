# Interface between client and the PictureServer
<hr>

**NOTE:** This Markdown file is best viewed with VisualStudio code (press CTRL shift v)

This document defines the wire protocol between an http client and the server in the project.

The words 'MUST', 'SHALL', 'SHOULD' are as defined in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)

The set of commands supported by the server may increase over time, with a change in the api version.

The server has an API VERSION. The current version is 1. This value MUST be returned in the `/status` endpoint.

In API VERSION 1, the server SHALL use http scheme. Clients MUST NOT follow redirects.

Connection handling: Clients MAY open or close connections at any time; the server does not guarantee persistent or keep-alive behavior.

If the client is browser: No CORS support required.

see [REST API](https://stackoverflow.blog/2020/03/02/best-practices-for-rest-api-design/)<br>
see [Idempotent commands](https://restfulapi.net/idempotent-rest-apis/)

# The Goal
An http server where one can create a user, log in and log out of it, and have images classified by an AI model while logged in.

## Authentication
This API enforces user authentication for core operations. Clients MUST authenticate by obtaining a session token via the `/login` endpoint.

For protected endpoints, the client MUST include the token in the HTTP `Authorization` header using the `Bearer` schema:
`Authorization: Bearer <token>`

If the header is missing, malformed, or the token is invalid/expired, the server SHALL return a `401 Unauthorized` status.

## Command format

When sending the image file, use FormData. For authentication endpoints, use JSON.

### Server response
The server SHALL respond with json body.

- server SHALL have Content-Type=application/json
- Response of the server SHALL have a json body. If the response is error, the body SHALL be:

```json
  {"error": {"http_status": number, "message": "some message"}}
```

The "http_status" field in the error object must exactly match the HTTP response code.
The HTTP status itself should also be the same number. (Meaning if for example the "http_status" returned is 400 then the server should send this json with the status code 400 and not 200).

### Response codes

The response codes SHALL be standard HTTP status codes. 

Each command specifies the possible status codes.

# Command list

## Register new user

This endpoint creates a new user account.

Endpoint: **POST /register**

Content-Type: application/json

The request body SHALL be a JSON object containing `username` and `password` strings.

### Example call

#### GOOD

```bash
curl -X POST http://localhost/register \
     -H "Content-Type: application/json" \
     -d '{"username": "testuser", "password": "securepassword123"}'

```

### Possible Response

201: user created successfully

400: malformed request (e.g., missing username or password fields)

405: unsupported http method

409: conflict (username already exists)

500: internal server error

If 201, the json body SHALL be `{"message": "User registered successfully"}`.

## Log in

This endpoint authenticates a user and returns a session token.

Endpoint: **POST /login**

Content-Type: application/json

The request body SHALL be a JSON object containing `username` and `password` strings.

### Example call

#### GOOD

```bash
curl -X POST http://localhost/login \
     -H "Content-Type: application/json" \
     -d '{"username": "testuser", "password": "securepassword123"}'

```

### Possible Response

200: authenticated successfully

400: malformed request (e.g., missing fields)

401: unauthorized (invalid username or password)

405: unsupported http method

500: internal server error

If 200, the json body SHALL contain the token:

```json
{"token": "eyJhbGciOiJIUzI1NiIsInR..."}

```

## Log out

This endpoint invalidates the user's current session token.

Endpoint: **POST /logout**

Authorization: Bearer

### Example call

```bash
curl -X POST http://localhost/logout \
     -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR..."

```

### Possible Response

200: logged out successfully (token invalidated)

401: unauthorized (missing or invalid token)

405: unsupported http method

500: internal server error

If 200, the json body SHALL be `{"message": "Logged out successfully"}`.

## Upload image file to inference engine

This endpoint is for uploading an image and waiting until a response is ready.
**Requires Authentication.**

Endpoint: **POST /classifier**

Authorization: Bearer

Content-Disposition: form-data; name="image"; filename="somepic.png"

Send a form field called `image` of type "form-data" that contains the file you want to upload (for example, `somepic.png`).

Content-Type: image/png    or image/jpeg

Supported image types SHALL be PNG and JPEG. The images uploaded MUST end in ".png" or ".jpeg".

### Example call

#### GOOD

```bash
curl -X POST http://localhost/classifier \
     -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR..." \
     -H "Content-Type: multipart/form-data" \
     -F "image=@./somepic.png;type=image/png"

```

#### BAD (Missing Token)

```bash
curl -i -X POST http://localhost/classifier -F "image=@./somepic.png"
# HTTP/1.1 401 Unauthorized
# Content-Type: application/json
# {"error":{"http_status":401,"message":"Missing or invalid token"}}

```

#### BAD (Malformed Input)

```bash
curl -i -X POST http://localhost/classifier \
     -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR..." \
     -F "image=@./bad.bin"
# HTTP/1.1 400 Bad Request
# Content-Type: application/json
# {"error":{"http_status":400,"message":"Unsupported image format"}}

```

Treat any non-decodable payload as malformed. In this case the server SHALL return 400 and increment the number of failed jobs.

If the file is classified (regardless if the classification is correct), return 200.

The server SHALL respond synchronously.

If processing is too slow (e.g. connection to a remote API server failed), the server MUST return 500 with appropriate message.

Timeout handling is not needed.

### Possible Response

200: command processed successfully

400: the input file is malformed (e.g. bad file type)

401: unauthorized (missing or invalid token)

405: unsupported http method (user called GET)

500: internal server error

If 200: the json body shall be in the format `{ "matches": [ {"name": string, "score": number}]}`

The "score" represents the confidence in this match. Number SHALL be 0.0 < score <= 1.0, and the sum of the scores given SHALL be a number between 0 and 1.

#### example

```json
{
  "matches":
     [{"name": "tomato", "score": 0.9},
      {"name":"carrot", "score": 0.02}]
}
```

## Get server status

Endpoint: **GET /status**

Authorization: Bearer <token>

**Requires Authentication.**

Response: 200

The response body SHALL be in the format:
```json
{"status":
  {
    "uptime": number /* seconds */,
    "processed":{
          "success": number,
          "fail": number
    },
    "health": "ok" |"error",
    "api_version": number
  }
}

```

**uptime** is the numbers of seconds since the server started (wallclock time). 




The uptime value is in fractional seconds, e.g. 55.6

**success** is the number of jobs completed successfully

**fail** is the number of jobs completed with some error 

The "health" SHALL be "ok" if classification can be done, and "error" otherwise.

In this context, a `job` is uploading an image in order to get the classification.

### Example

```bash
curl -X GET http://localhost/status \
     -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR..."

```

with response

```json
{
  "status": {
    "uptime": 230.7,
    "processed":{
          "success": 5,
          "fail": 1
    },
    "health": "ok",
    "api_version": 1
  }
}

```

### Possible Response

200: command processed successfully

401: unauthorized (missing or invalid token)

405: unsupported http method

500: internal server error