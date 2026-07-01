import transformers
import torch
from transformers import BitsAndBytesConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from deepeval.models import DeepEvalBaseLLM
from pydantic import BaseModel
from lmformatenforcer import JsonSchemaParser
from lmformatenforcer.integrations.transformers import (
    build_transformers_prefix_allowed_tokens_fn,
)
import json
import signal
import functools
#from langchain.llms import Ollama
from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import PromptTemplate #, LLMChain
#from langchain_community.llms.huggingface_pipeline import HuggingFacePipeline


cache_dir = '/mnt/llm_models'

B_INST, E_INST = "[INST]", "[/INST]"
B_SYS, E_SYS = "<<SYS>>\n", "\n<</SYS>>\n\n"



def timeout(seconds=150, default=None):
	def decorator(func):
		@functools.wraps(func)
		def wrapper(*args, **kwargs):
			def handle_timeout(signum, frame):
				raise TimeoutError()
			#
			signal.signal(signal.SIGALRM, handle_timeout)
			signal.alarm(seconds)
			result = func(*args, **kwargs)
			signal.alarm(0)
			return result
		return wrapper
	return decorator


@timeout(seconds=150, default=None)
def get_response(pipeline, prompt, prefix_function):
	response = pipeline(prompt, prefix_allowed_tokens_fn=prefix_function)
	return response

def get_complete_response(pipeline, prompt, prefix_function):
	response = 'None'
	i = 10
	while response == 'None':
		try:
			response = get_response(pipeline, prompt, prefix_function)
		except TimeoutError:
			response = 'None'
		if i > 10:
			if response == 'None':
				response = [{'generated_text': '%s \n  \t\t\t   {"answer": "None."} \n  \t\t\t   \t\t' % prompt }]
			break
	return response


def get_default_json_if_broken(schema):
	default_val_dict = {'statements':'Broken JSON', 'verdict':'no', 'reason': 'Broken JSON'}
	schema_dict = json.loads(schema.schema_json(indent=2))
	print(schema_dict)
	fake_json = {}
	for prop in schema_dict['required']:
		main_type = schema_dict["properties"][prop]['type']
		if main_type == 'array':
			fake_json[prop] = []
			if 'type' in schema_dict["properties"][prop]['items']:
				fake_json[prop] = [default_val_dict[prop]]
			else:
				sub_prop_def = schema_dict["properties"][prop]['items']['$ref'][8:]
				sub_dict = {}
				for sub_prop in schema_dict['$defs'][sub_prop_def]['required']:
					sub_dict[sub_prop] = default_val_dict[sub_prop]
				fake_json[prop].append(sub_dict)
			#print(fake_json)
		else:
			fake_json[prop] = default_val_dict[prop]
	return fake_json




class OllamaCustomLLMforEval(DeepEvalBaseLLM):
	def __init__(self, model_name):
		#
		self.model_name = model_name
		self.model = OllamaLLM(model=model_name)
		self.template = ''
	#
	def load_model(self):
		return self.model
	#
	def set_template(self, instruction, new_system_prompt):
		system_prompt = B_SYS + new_system_prompt + E_SYS
		self.template = B_INST + system_prompt + instruction + E_INST
	#
	def set_context(self, context):
		self.context = context 
	#
	def generate(self, prompt: str, schema: BaseModel) -> BaseModel:
		#print(prompt)
		model = self.load_model()
		prompt_template = PromptTemplate(template=self.template, input_variables=["context", "question"])
		llm_chain = prompt_template | model
		response = {}
		if str(schema)=="<class 'compare_models.Answer'>":
			output = llm_chain.invoke({'context':self.context, 'question':prompt})
			#print(output)
			response = {'answer':output}
		else:
			#print(schema.schema_json(indent=2))
			output = model.invoke(prompt)
			try:
				response = json.loads(output)
			except json.decoder.JSONDecodeError:
				response = get_default_json_if_broken(schema)
				print(prompt)
		return schema(**response)
	#
	async def a_generate(self, prompt: str, schema: BaseModel) -> BaseModel:
		return self.generate(prompt, schema)
	#
	def get_model_name(self):
		return self.model_name
	#
	def get_llm_output(self, input_dict, input_variables=["context", "question"]):
		#print(self.template, input_dict.items())
		model = self.load_model()
		model.temperature = 0
		prompt_template = PromptTemplate(template=self.template, input_variables=input_variables)
		llm_chain = prompt_template | model
		output = llm_chain.invoke(input_dict)
		print(output)
		return output


