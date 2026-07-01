import falcon
import json
import logging
import os
import pandas as pd
import numpy as np
from ollama_llm import OllamaCustomLLMforEval
from mdm_model_interactive import get_stage_response_interactive


class GetInteractiveNextStageHandler(object):
	def __init__(self, manager):
		self.current_model = OllamaCustomLLMforEval(manager[1])
		self.action_list_dict = manager[0]
	#
	#def on_get(self, req, resp, input_type:str, ehr_token:str, new_stage:str, user_inputs:dict):
	def on_get(self, req, resp):
		path = req.path
		print('get')
		#
		#
		resp.status = falcon.HTTP_200
		resp.text = json.dumps(response_dict)
		return
	#
	def on_post(self, req, resp):
		path = req.path
		inputs = req.params
		response_dict = get_response_dict(self.current_model, self.action_list_dict, inputs["input_type"], inputs["ehr_token"], inputs["new_stage"],inputs["user_inputs"])
		resp.status = falcon.HTTP_200
		resp.text = json.dumps(response_dict)
		return



def get_response_dict(current_model, action_list_dict, input_type, ehr_token, new_stage, user_inputs):
	print(user_inputs)
	user_input = json.loads(user_inputs)
	if "user_input" in user_input:
		user_input = user_input["user_input"]
		if len(user_input) == 1:
			user_input = user_input[0]
	print(user_input)
	#
	cm_medical_info, new_stage, prompt_dict = get_stage_response_interactive(current_model, input_type, ehr_token, new_stage, user_input)
	next_test = 'next'
	if '|' in new_stage:
		new_stage, next_test = new_stage.split('|')
	#
	response_dict = {}
	response_dict["new_stage"] = new_stage
	response_dict["next_test"] = next_test
	response_dict["elapsed_time"] = cm_medical_info.elapsed_time
	response_dict["seen_stages"] = cm_medical_info.seen_stages
	response_dict["possible_diag"] = cm_medical_info.early_diseases
	response_dict["low_severity_diag"] = cm_medical_info.low_severity_diag
	response_dict["high_severity_diag"] = cm_medical_info.high_severity_diag
	response_dict["eliminated_diag"] = cm_medical_info.eliminated_diag
	response_dict["rx_list"] = cm_medical_info.rx_list
	response_dict["EHR"] = cm_medical_info.cm_info_dict
	response_dict["action_list"] = return_action_lists(new_stage, cm_medical_info, action_list_dict)
	response_dict["prompt_dict"] = json.dumps(prompt_dict)
	print(response_dict)
	return response_dict

def return_action_lists(new_stage, cm_medical_info, action_list_dict):
	action_option_list = []
	if new_stage in ['Initial Assessment Stage', 'Differential Diagnosis Stage']:
		action_option_list = list(set(action_list_dict[new_stage])-set(cm_medical_info.seen_actions))
	elif new_stage=='Monitoring Stage':
		if 'Monitoring Stage' in cm_medical_info.seen_stages[-1]:
			action_option_list = list(set(action_list_dict[new_stage])-set(cm_medical_info.seen_actions))
	elif new_stage=='Intervention Stage':
		action_option_list = action_list_dict[new_stage].to_json(orient="split")
	return action_option_list


