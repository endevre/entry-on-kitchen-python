# Kitchen Module Documentation
## EntryBlock Class

The EntryBlock class is a part of the kitchen module for accessing entry blocks. It provides methods for both synchronous and asynchronous execution, as well as asynchronous and synchronous methods for getting run status.

### Methods

1. **`__init__(pipelineId, entryBlockId, entryPoint, entryAuthCode)`**

    Initializes a new EntryBlock instance with the specified pipeline ID, entry block ID, entry point, and entry authentication code.

    Parameters:
    - `pipelineId` (ObjectId, required): The ID of the pipeline.
    - `entryBlockId` (str, required): The ID of the entry block.
    - `entryPoint` (str, defaults to None): The entry point for the pipeline. (None for production, beta for beta)
    - `entryAuthCode` (str, defaults to None): The entry auth code associated with the account

2. **`runSync(input_data)`**

    Executes the entry block synchronously and returns the response.

    Parameters:
    - `input_data` (dict): Input data to be passed to the entry block.

    Returns:
    - `response` (dict): The response from the entry block.

3. **`async runAsync(input_data)`**

    Executes the entry block asynchronously and returns the response.

    Parameters:
    - `input_data` (dict): Input data to be passed to the entry block.

    Returns:
    - `response` (dict): The response from the entry block.

4. **`pollStatus(runId)`**

    - Polls the status of a pipeline run synchronously.

    - Parameters:
        - `runId` (str): The ID of the pipeline run to poll.

    - Returns:
        - `status` (dict): The status of the pipeline run.

5. **`async pollStatusAsync(runId)`**

    - Polls the status of a pipeline run asynchronously.

    - Parameters:
        - `runId` (str): The ID of the pipeline run to poll.

    - Returns:
        - `status` (dict): The status of the pipeline run.

---

These additions provide documentation for the `pollStatus` and `pollStatusAsync` methods, including their parameters, return types, and usage examples for both synchronous and asynchronous calls.



### Example Usage:
```py
from entry_on_kitchen.Kitchen import EntryBlock

# Synchronous call
entry = EntryBlock(pipelineId="pipelineId", 
                   entryBlockId="entryBlockId", 
                   entryPoint="beta", 
                   entryAuthCode="authCode")
response = entry.runSync(input_data)
print(response)

# Asynchronous call
import asyncio

async def async_call():
    entry = EntryBlock(pipelineId="pipelineId", 
                   entryBlockId="entryBlockId", 
                   entryPoint="beta", 
                   entryAuthCode="authCode")
    response = await entry.runAsync(input_data)
    print(response)

asyncio.run(async_call())
```