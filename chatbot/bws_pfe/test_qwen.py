import os
from dotenv import load_dotenv

load_dotenv('D:/bws_pfe/.env')

hf_key   = os.getenv('HF_API_KEY')
hf_model = os.getenv('HF_MODEL', 'Qwen/Qwen2.5-7B-Instruct')

print(f'Clé HF  : {hf_key[:8]}...[HIDDEN]')
print(f'Modèle  : {hf_model}')
print('Test en cours...')

from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from langchain_core.messages import HumanMessage

llm = HuggingFaceEndpoint(
    repo_id                  = hf_model,
    huggingfacehub_api_token = hf_key,
    temperature              = 0.1,
    max_new_tokens           = 200,
    task                     = 'conversational',
)

chat = ChatHuggingFace(llm=llm)
result = chat.invoke([HumanMessage(content='Réponds uniquement en français : Bonjour, tu es qui ?')])
print(f'\nQwen OK ✓\nRéponse : {result.content}')