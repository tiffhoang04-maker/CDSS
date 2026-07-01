import falcon
import json
import logging
import os
import pandas as pd
import numpy as np
from ollama_llm import OllamaCustomLLMforEval
from mdm_model import get_stage_response

# (2) main non-interactive decision loop - controls one full backend step of the MDM workflow
# given a current EHR token and stage, this loads or creates a MedicalInformation object 
# then runs the appropriate stage logic 
# then asks the LLM what emergency stage should be next 
# persists progress in memory cache

class GetNextStageHandler(object):
	def __init__(self, manager):
		self.current_model = OllamaCustomLLMforEval(manager[1])
		self.action_list_dict = manager[0]
		self.medical_info_cache = manager[2]
	#
	def on_get(self, req, resp, input_type:str, ehr_token:str, new_stage:str):
		path = req.path
		print('get')
		#
		cm_medical_info, new_stage = get_stage_response(self.current_model, input_type, ehr_token, new_stage, self.medical_info_cache)
		response_dict = {}
		response_dict["new_stage"] = new_stage
		response_dict["elapsed_time"] = cm_medical_info.elapsed_time
		response_dict["seen_stages"] = cm_medical_info.seen_stages
		response_dict["possible_diag"] = cm_medical_info.early_diseases
		response_dict["low_severity_diag"] = cm_medical_info.low_severity_diag
		response_dict["high_severity_diag"] = cm_medical_info.high_severity_diag
		response_dict["eliminated_diag"] = cm_medical_info.eliminated_diag
		response_dict["rx_list"] = cm_medical_info.rx_list
		response_dict["EHR"] = cm_medical_info.cm_info_dict
		response_dict["action_list"] = return_action_lists(new_stage, cm_medical_info, self.action_list_dict)
		#
		print(response_dict)
		#
		resp.status = falcon.HTTP_200
		resp.text = json.dumps(response_dict)
		return
	#
	def on_post(self, req, resp):
		path = req.path
		resp.status = falcon.HTTP_200
		resp.text = "\n"
		return


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



