# Entry on Kitchen Python Library
[![PyPI - Downloads](https://img.shields.io/pypi/dm/entry-on-kitchen)](https://pypi.org/project/entry-on-kitchen/)
[![PyPI - Version](https://img.shields.io/pypi/v/entry-on-kitchen)](https://pypi.org/project/entry-on-kitchen/)

Official Python module for executing recipes on the Entry on Kitchen API. Supports both synchronous execution and real-time HTTP streaming.

## Installation

```bash
pip install entry-on-kitchen
```

## Quick Start

```python
from entry_on_kitchen import KitchenClient

# Initialize the client with your auth code
client = KitchenClient(
    auth_code="your-auth-code-here",
    entry_point="beta"  # Optional: use "" for production
)

# Synchronous execution
result = client.sync(
    recipe_id="your-recipe-id",
    entry_id="your-entry-id",
    body={"message": "Hello, Kitchen!"}
)

print(result)
```

## KitchenClient Class

The `KitchenClient` class provides a simple interface for executing recipes.

### Constructor

```python
KitchenClient(auth_code, entry_point="")
```

**Parameters:**
- `auth_code` (str, required): Your X-Entry-Auth-Code for authentication
- `entry_point` (str, optional): Entry point environment (e.g., "beta" for beta). Defaults to "" (production)

**Raises:**
- `ValueError`: If `auth_code` is not provided or empty

### Methods

#### `sync(recipe_id, entry_id, body, use_kitchen_billing=False, llm_override=None, api_key_override=None)`

Execute a recipe synchronously and wait for the complete result.

**Parameters:**
- `recipe_id` (str): The ID of the pipeline/recipe
- `entry_id` (str): The ID of the entry block
- `body` (dict or str): Request body data
- `use_kitchen_billing` (bool, optional): Enable Kitchen billing
- `llm_override` (str, optional): Override the LLM model (e.g., "gpt-4", "claude-3")
- `api_key_override` (dict, optional): Override API keys for external services

**Returns:**
Dictionary containing:
- `runId`: The execution run ID
- `status`: Execution status ("finished", "error", etc.)
- `result`: The execution result (if successful)
- `error`: Error message (if failed)
- `exitBlock`: Exit block information

**Example:**
```python
result = client.sync(
    recipe_id="recipe-123",
    entry_id="entry-456",
    body={
        "message": "Hello!",
        "provider": "google_genai",
        "model": "gemini-2.5-flash"
    }
)

if result["status"] == "finished":
    print("Success:", result["result"])
else:
    print("Error:", result["error"])
```

#### `stream(recipe_id, entry_id, body, use_kitchen_billing=False, llm_override=None, api_key_override=None)`

Execute a recipe with real-time streaming. Yields events as they arrive.

**Parameters:**
- `recipe_id` (str): The ID of the pipeline/recipe
- `entry_id` (str): The ID of the entry block
- `body` (dict or str): Request body data
- `use_kitchen_billing` (bool, optional): Enable Kitchen billing
- `llm_override` (str, optional): Override the LLM model (e.g., "gpt-4", "claude-3")
- `api_key_override` (dict, optional): Override API keys for external services

**Yields:**
Dictionary objects representing stream events with keys:
- `runId`: The execution run ID
- `type`: Event type (see types below)
- `time`: Timestamp of the event
- `data`: Event-specific data
- `socket`: Socket ID (for "result" and "delta" events)
- `statusCode`: HTTP status code

**Event Types:**
- `"progress"`: Execution progress updates
- `"result"`: Output data from blocks
- `"delta"`: Incremental content updates (for streaming LLM responses)
- `"info"`: Informational messages
- `"end"`: Final result (marks completion)

**Example:**
```python
for event in client.stream(
    recipe_id="recipe-123",
    entry_id="entry-456",
    body={"message": "Hello!"}
):
    event_type = event["type"]

    if event_type == "progress":
        data = event["data"]
        print(f"Progress: {data['blockPosition']}/{data['blocksToExitBlock']}")

    elif event_type == "result":
        socket = event["socket"]
        data = event["data"]
        print(f"Result from {socket}: {data}")

    elif event_type == "delta":
        socket = event["socket"]
        delta = event["data"]
        print(f"Delta update for {socket}: {delta}")

    elif event_type == "end":
        print("Complete!")
        print(f"Final result: {event['data']}")
```

#### `stream_raw(recipe_id, entry_id, body)`

Execute a recipe with streaming, yielding raw JSON strings. Useful for custom parsing.

**Example:**
```python
for raw_json in client.stream_raw(
    recipe_id="recipe-123",
    entry_id="entry-456",
    body={"message": "Hello!"}
):
    print(raw_json)
```

## Complete Examples

### Synchronous Execution

```python
from entry_on_kitchen import KitchenClient

client = KitchenClient(auth_code="your-auth-code", entry_point="beta")

result = client.sync(
    recipe_id="my-recipe",
    entry_id="my-entry",
    body={"input": "value"}
)

print(f"Run ID: {result['runId']}")
print(f"Status: {result['status']}")
print(f"Result: {result.get('result')}")
```

### Streaming with Progress Tracking

```python
from entry_on_kitchen import KitchenClient

client = KitchenClient(auth_code="your-auth-code")

result_buffer = {}

for event in client.stream(
    recipe_id="my-recipe",
    entry_id="my-entry",
    body={"input": "value"}
):
    if event["type"] == "progress":
        # Show progress
        block = event["data"]["blockPosition"]
        total = event["data"]["blocksToExitBlock"]
        print(f"\rProgress: {block}/{total} blocks", end="", flush=True)

    elif event["type"] == "result":
        # Store results
        socket = event["socket"]
        result_buffer[socket] = event["data"]
        print(f"\nReceived result from {socket}")

    elif event["type"] == "end":
        print("\nExecution complete!")
        print(f"Final result: {event['data']}")

print("\nAll results:", result_buffer)
```

### Streaming LLM Responses

```python
from entry_on_kitchen import KitchenClient

client = KitchenClient(auth_code="your-auth-code")

full_response = ""

for event in client.stream(
    recipe_id="llm-recipe",
    entry_id="llm-entry",
    body={"prompt": "Tell me a story"}
):
    if event["type"] == "delta":
        # Delta updates contain incremental text
        for op in event["data"]:
            if op[0] == "i":  # Insert operation
                position, length, text = op[1], op[2], op[3]
                full_response += text
                print(text, end="", flush=True)

    elif event["type"] == "end":
        print("\n\nComplete!")
```

## Environment Configuration

### Production
```python
client = KitchenClient(auth_code="your-auth-code", entry_point="")
# Uses: https://entry.on.kitchen
```

### Beta
```python
client = KitchenClient(auth_code="your-auth-code", entry_point="beta")
# Uses: https://beta.entry.on.kitchen
```

### Custom Entry Point
```python
client = KitchenClient(auth_code="your-auth-code", entry_point="custom")
# Uses: https://custom.entry.on.kitchen
```

## Optional Features

### Kitchen Billing

Enable Kitchen billing for your recipe execution:

```python
result = client.sync(
    recipe_id="recipe-123",
    entry_id="entry-456",
    body={"message": "Hello!"},
    use_kitchen_billing=True
)
```

### LLM Model Override

Override the LLM model used in your recipe:

```python
result = client.sync(
    recipe_id="recipe-123",
    entry_id="entry-456",
    body={"message": "Write a poem"},
    llm_override="gpt-4"
)

# Or with streaming
for event in client.stream(
    recipe_id="recipe-123",
    entry_id="entry-456",
    body={"message": "Write a poem"},
    llm_override="claude-3"
):
    # Handle events
    pass
```

### Combining Options

You can use both options together:

```python
result = client.sync(
    recipe_id="recipe-123",
    entry_id="entry-456",
    body={"message": "Hello!"},
    use_kitchen_billing=True,
    llm_override="gpt-4"
)
```

## Requirements

- Python 3.7 or higher
- `requests` library

## Error Handling

```python
from entry_on_kitchen import KitchenClient
import requests

client = KitchenClient(auth_code="your-auth-code")

try:
    result = client.sync(
        recipe_id="recipe-123",
        entry_id="entry-456",
        body={"input": "value"}
    )
except requests.HTTPError as e:
    print(f"HTTP Error: {e}")
except ValueError as e:
    print(f"Value Error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Migration from v0.x

Version 0.3.0 is a breaking change from v0.x. Here's how to migrate:

### Old API (v0.x)
```python
from entry_on_kitchen.Kitchen import EntryBlock

entry = EntryBlock(
    pipelineId="recipe-123",
    entryBlockId="entry-456",
    entryAuthCode="your-auth-code",
    entryPoint="beta"
)

# Synchronous
result = entry.runSync(input_data)

# Asynchronous with polling
result = await entry.runAsync(input_data)
```

### New API (v0.3.0)
```python
from entry_on_kitchen import KitchenClient

client = KitchenClient(
    auth_code="your-auth-code",
    entry_point="beta"
)

# Synchronous
result = client.sync(
    recipe_id="recipe-123",
    entry_id="entry-456",
    body=input_data
)

# Streaming (replaces async/polling)
for event in client.stream(
    recipe_id="recipe-123",
    entry_id="entry-456",
    body=input_data
):
    handle_event(event)
```

## License

Copyright © Endevre Technologies

## Support

For issues and questions, contact: contact@endevre.com
