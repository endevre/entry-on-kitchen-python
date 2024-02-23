import requests
import json
import time
import aiohttp
import asyncio

class EntryBlock:
    def __init__(self, pipelineId=None, entryBlockId=None, entryAuthCode=None, entryPoint=""):
        if not pipelineId or not entryBlockId:
            raise ValueError('pipelineId and entryBlockId are required')

        self.pipelineId = pipelineId
        self.entryBlockId = entryBlockId
        self.entryPoint = entryPoint
        self.entryAuthCode = entryAuthCode

    def runSync(self, body):
        result = None
        resolved = False

        headers = {
            'Content-Type': 'application/json',
            'X-Entry-Auth-Code': self.entryAuthCode,
        }

        entryPoint = self.entryPoint + "." if self.entryPoint else ""

        stringifiedBody = body if isinstance(body, str) else json.dumps(body)

        response = requests.post(
            f"https://{entryPoint}entry.on.kitchen/{self.pipelineId}/{self.entryBlockId}/sync",
            data=stringifiedBody,
            headers=headers
        )

        result = response.json() if response.ok else response.json()

        return result

    def pollStatus(self, runId):
        status = None
        resolved = False

        headers = {
            'Content-Type': 'application/json',
            'X-Entry-Auth-Code': self.entryAuthCode,
        }

        entryPoint = self.entryPoint + "." if self.entryPoint else ""

        response = requests.get(
            f"https://{entryPoint}entry.on.kitchen/{self.pipelineId}/pollstatus/{runId}",
            headers=headers
        )

        status = response.json() if response.ok else response.json()

        return status

    async def pollStatusAsync(self, runId):
        headers = {
            'Content-Type': 'application/json',
            'X-Entry-Auth-Code': self.entryAuthCode,
        }

        entryPoint = self.entryPoint + "." if self.entryPoint else ""

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://{entryPoint}entry.on.kitchen/{self.pipelineId}/pollstatus/{runId}",
                headers=headers
            ) as response:
                return await response.json(content_type=None)

    async def runAsync(self, body):
        headers = {
            'Content-Type': 'application/json',
            'X-Entry-Auth-Code': self.entryAuthCode,
        }

        entryPoint = self.entryPoint + "." if self.entryPoint else ""

        stringifiedBody = body if isinstance(body, str) else json.dumps(body)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://{entryPoint}entry.on.kitchen/{self.pipelineId}/{self.entryBlockId}/async",
                data=stringifiedBody,
                headers=headers
            ) as response:
                if response.status == 200:
                    result = await response.json(content_type=None)
                    runId = result['runId']
                    while True:
                        status = await self.pollStatusAsync(runId)
                        if status['status'] == "finished":
                            return status
                        elif status['status'] == "running":
                            await asyncio.sleep(1)
                        else:
                            return status
                else:
                    raise Exception('Unable to runAsync:', await response.text())