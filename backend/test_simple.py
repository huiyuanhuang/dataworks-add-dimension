#!/usr/bin/env python3
import requests
import json

LLM_API_URL = "http://47.236.3.167:8080/v1/chat/completions"
LLM_API_KEY = "sk-b73a46c0c22f8f155c54ba360248df125e825364dffecb7c3cb4e3ac224dabf2"
LLM_MODEL = "gpt-5.4"

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {LLM_API_KEY}"
}

payload = {
    "model": LLM_MODEL,
    "messages": [
        {"role": "system", "content": "You are an ODPS SQL analyst."},
        {"role": "user", "content": "Analyze this SQL and return a JSON with expansion_type, upstream_tables, issues:\nSELECT cou, ver, cha, active_uv FROM dwr_spock_test2_1d GROUP BY cou, ver, cha"}
    ],
    "temperature": 0.3,
    "max_tokens": 2000
}

try:
    response = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()
    result = data['choices'][0]['message']['content'].strip()
    print("✅ LLM test success!")
    print(f"Response: {result[:200]}...")
except Exception as e:
    print(f"❌ LLM test failed: {e}")
