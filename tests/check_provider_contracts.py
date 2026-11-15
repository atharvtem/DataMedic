"""Offline HTTP contract checks; makes no external API requests."""
import asyncio
import json
import os
from unittest.mock import patch
import httpx
from datamedic.agent.llm import LLMPlanner, Decision

async def main():
    for provider in ['groq','gemini']:
        def handler(request):
            body=json.loads(request.content)
            text=json.dumps({'request':{'tool':'inspect_database_schema','arguments':{}}})
            if provider=='groq':
                assert request.headers['authorization']=='Bearer test-key'
                assert body['model']=='openai/gpt-oss-120b'
                return httpx.Response(200,json={'choices':[{'message':{'content':text}}],'usage':{'total_tokens':19},'model':'openai/gpt-oss-120b'})
            assert request.headers['x-goog-api-key']=='test-key'
            return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':text}]}}],'usageMetadata':{'totalTokenCount':23},'modelVersion':'served-test-model'})
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch.dict(os.environ,{provider.upper()+'_API_KEY':'test-key'}), patch('datamedic.agent.llm.httpx.AsyncClient',return_value=client):
            planner=LLMPlanner(provider)
            result=await planner.generate({'task':'test'},Decision)
            assert result.request.tool=='inspect_database_schema'
            assert planner.tokens in [19,23]
            assert planner.calls[0]['served_model']
    print('Passed Groq/Gemini offline HTTP contracts, parsed requests, token accounting, served-model capture')
asyncio.run(main())
