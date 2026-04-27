import sys
import os
from app import gemini_generator, template_generator
import json

req = {'website_name': 'Test', 'website_type': 'technology', 'description': 'Startup', 'images': [], 'pages': 'Home'}

try:
    res = gemini_generator(req)
    with open('gemini_out.json', 'w', encoding='utf-8') as f:
        json.dump(res, f, indent=2)
    print("GEMINI SUCCESS")
except Exception as e:
    print(f"GEMINI FAILED: {str(e)}")
    
try:
    res2 = template_generator(req)
    with open('template_out.json', 'w', encoding='utf-8') as f:
        json.dump(res2, f, indent=2)
    print("TEMPLATE SUCCESS")
except Exception as e:
    print(f"TEMPLATE FAILED: {str(e)}")
