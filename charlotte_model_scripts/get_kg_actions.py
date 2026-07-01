import pandas as pd
import time
import numpy as np
import json
import re
from datetime import datetime, timedelta
from ast import literal_eval
import os

# (4) executes selected medical actions and writes results into the patient record
# ex: if model chooses vitals, labs, symptom reassessment, or a survey then this file picks which results get added to the health record

test_dir='interactive_assessment'


# for canned data reassass vitals / symptoms only set up to be ran once
# filename, synthetic, interactive
canned_options = ['Pneumothorax']


addl_action_list = ["Diagnose crew member.", "Prescribe medication.", "Nothing more to do."]
end_differential_actions = ["Nothing more to do."]
end_initial_assessment_actions = ["Diagnose crew member.", "Nothing more to do."]

# made with make_kg_actions_and_nt_embeddings (kg=exmc) 
# make_kg_actions_and_nt_embeddings(kg, test_dir, all_possible_actions, early_tests, monitor_actions)
from get_embeddings_for_tests import load_vectorstore, create_vectordb
actions_vectorstore = load_vectorstore('tests/'+ test_dir, ['kg_action_options', 'emergency_stage_options', 'Condition', 'Symptom', 'Disease', 'MedKit'])

def open_gds(session_name='ALT', db='exmc'):
	from graphdatascience import GraphDataScience
	auth=('neo4j', os.getenv(session_name+'_NEO4J_P_1'))
	return GraphDataScience(os.getenv(session_name+'_NEO4J_URI_1'), auth=auth, database=db)

def load_canned_data(input_type):
	canned = {}
	if input_type not in ['synthetic', 'interactive']:
		with open(input_type, 'r') as file:
			canned = json.loads(''.join(file.readlines()))
	return canned

class KGActionStore():
	def __init__(self, input_type):
		#
		self.input_type = input_type
		self.kg = open_gds(session_name='ALT', db='exmc')
		self.canned = load_canned_data(input_type)
		#
	#
	def get_results(self, cm_medical_info, test):
		query = """MATCH (n:Action {name:"%s"}) RETURN n.identifier, n.output_type, n.is_category, n.is_monitoring, n.duration"""
		identifier, test_type, is_category, is_monitoring, duration = self.kg.run_cypher(query % test).values[0]
		#print(identifier, test_type, is_category, is_monitoring, duration)
		if is_monitoring:
			if test == "Reassess crew member's vitals.":
				cm_medical_info = self.get_reassess_vitals(cm_medical_info)
			elif test == "Reassess crew member's symptoms.":
				#print('here')
				cm_medical_info = self.reassess_symptoms(cm_medical_info, symptoms_list=['Chest pain', 'Short of breath'])
			else:
				cm_medical_info.elapsed_time = cm_medical_info.elapsed_time+duration
		else:
			test_list = [identifier]
			category = test.upper()
			if is_category == True:
				query = "MATCH (n:Action {identifier:'%s'})-[:CONTAINS_AcA*]->(n2:Action) WHERE n2.is_category IS NULL RETURN n2.identifier as i"
				subcategories = list(self.kg.run_cypher(query % identifier).i.unique())
				test_list = subcategories if len(subcategories) > 0 else test_list
			else:
				query = "MATCH (n:Action {identifier:'%s'})<-[:CONTAINS_AcA]-(n2:Action) WHERE  n2.is_category =true RETURN n2.name as i"
				category = self.kg.run_cypher(query % identifier).i.values[0].upper()
			if category not in cm_medical_info.cm_info_dict:
				cm_medical_info.cm_info_dict[category]='\n'
			query = "MATCH (n) WHERE n.identifier IN %s AND n.is_action=true RETURN n.name as name, n.output_type, n.output_params, n.normal_range, n.output_format, n.duration"
			test_info_df = self.kg.run_cypher(query % test_list)
			cm_medical_info.seen_actions+=list(test_info_df.name.unique())
			results, full_duration = self.get_action_result(test_info_df)
			#
			cm_medical_info.elapsed_time = cm_medical_info.elapsed_time+full_duration
			curr_time = cm_medical_info.get_current_time()
			cm_medical_info = self.add_results_to_record(cm_medical_info, curr_time, results, category)
		#cm_medical_info.seen_actions+=[test]
		return cm_medical_info
	#
	def get_action_result(self, test_info_df):
		results = {}
		full_duration = 0
		if len(test_info_df)>0:
			for test_name, test_type, test_options, normal_range, output_format, duration in test_info_df.values:
				full_duration+=duration
				if test_type == 'Discrete':
					results[test_name] = self.get_discrete_results(test_name, test_options)
				elif test_type in ['Normal', 'Gamma']:
					test_func = np.random.normal if test_type=='Normal' else np.random.gamma
					results[test_name] = self.get_range_result(test_name, test_options, normal_range, output_format, test_func)
				else:
					print('Unknown test type: %s' % test_name)
		else:
			print('ERROR')
			print(test)
			print('TEST MISSING')
		return results, full_duration
	#
	def get_discrete_results(self, test_name, test_options):
		if self.input_type == 'synthetic':
			return np.random.choice(test_options, 1)[0]
		elif self.input_type == 'interactive':
			return input('Please enter the %s results:\n' % test_name)
		else:
			return self.canned[test_name]
	#
	def get_range_result(self, test_name, test_options, normal_range, output_format, test_func):
		float_list = ['temperature']
		if (self.input_type == 'synthetic') or (self.input_type == 'interactive'):
			result, result_type = 0, ' (Normal)'
			if self.input_type == 'synthetic':
				result = test_func(test_options[0], test_options[1], 1)[0]
				if test_func == np.random.gamma:
					if test_options[-1]==1:
						result = 1-result
					if "%%" in output_format:
						result = result*100
				if test_name not in float_list:
					result = int(result)
				else:
					result = np.round(result, 1)
			elif self.input_type == 'interactive':
				result = input('Please enter the %s results. The normal range is %s-%s:\n' % (test_name, normal_range[0], normal_range[1]))
				if test_name not in float_list:
					result = int(float(result))
				else:
					result = np.round(float(result), 1)
			result_type = ' (Low)' if result < normal_range[0] else result_type
			result_type = ' (High)' if result > normal_range[0] else result_type
			result = (output_format % result)+result_type
			return result
		else:
			return self.canned[test_name]
	#
	def get_reassess_vitals(self, cm_medical_info):
		query = "MATCH (n:Action {name:'Vitals'})-[:CONTAINS_AcA*]->(n2:Action) WHERE n2.is_category IS NULL RETURN DISTINCT n2.identifier as i"
		test_list = list(self.kg.run_cypher(query).i.unique())
		query = "MATCH (n) WHERE n.identifier IN %s AND n.is_action=true RETURN DISTINCT n.name, n.output_type, n.output_params, n.normal_range, n.output_format, n.duration"
		test_info_df = self.kg.run_cypher(query % test_list)
		#
		results, full_duration = {},0
		if (self.input_type == 'synthetic') or (self.input_type == 'interactive'):
			results, full_duration = self.get_action_result(test_info_df)
		else:
			results, full_duration = self.canned['reassess_vitals'], 15
		#
		cm_medical_info.elapsed_time = cm_medical_info.elapsed_time+full_duration
		curr_time = cm_medical_info.get_current_time()
		cm_medical_info = self.add_results_to_record(cm_medical_info, curr_time, results, 'VITALS')
		return cm_medical_info
	#
	def add_results_to_record(self, cm_medical_info, curr_time, results, test):
		add_str = ''.join(['\n%s %s: %s' % (curr_time, k, v) for k, v in results.items()])
		cm_medical_info.cm_info_dict[test.upper()] = cm_medical_info.cm_info_dict[test.upper()]+add_str
		return cm_medical_info
	#
	def reassess_symptoms(self, cm_medical_info, symptoms_list=['Chest pain', 'Short of breath']):
		response = []
		if (self.input_type == 'synthetic') or (self.input_type == 'interactive'):
			response = self.check_symptoms(response, symptoms_list)
			answer = input("Do you have any new symptoms? Respond: yes=Y no=N\n") if self.input_type == 'interactive' else get_random_answer(['Y', 'N'])
			if answer == 'Y':
				response = self.new_symptoms(response)
		else:
			response = self.canned['reassess_pain_survey']
		#
		cm_medical_info.elapsed_time = cm_medical_info.elapsed_time+15
		curr_time = cm_medical_info.get_current_time()
		results = ''.join(['\n%s %s' % (curr_time, result) for result in response])
		cm_medical_info.cm_info_dict['EHRS'] = cm_medical_info.cm_info_dict['EHRS']+results
		return cm_medical_info
	#
	def check_symptoms(self, response, symptoms_list):
		for symptom in symptoms_list:
			if self.input_type == 'interactive':
				answer = input("Have your %s symptoms have improved? Respond: 'worsened', 'stayed the same', or 'improved'\n" % symptom)
				response.append("%s symptoms have %s." % (symptom, answer))
			else:
				response.append("%s symptoms have %s." % (symptom, get_random_answer(['worsened', 'stayed the same', 'improved'])))
		return response
	#
	def new_symptoms(self, response):
		answer = 'Start'
		if self.input_type == 'interactive':
			prompt = "List your new symptoms one at a time (pressing return in between). When you are finish, respond: 'DONE'.\n"
			response = get_multi_interactive(prompt, format_str="Began experiencing %s.")
		else:
			n_new = get_random_answer(np.arange(0,4))
			if n_new>0:
				possible_symptoms = self.get_possible_symptoms()
				for symptom in np.random.choice(possible_symptoms, n_new):
					response.append("Began experiencing %s." % symptom)
		return response
	#
	def get_initial_interaction(self, test_dir, cm_medical_info):
		cm_medical_info = self.load_patient_history(test_dir, cm_medical_info)
		response = []
		if self.input_type == 'interactive':
			prompt = "Please state the nature of the medical emergency.\nList your new symptoms one at a time (pressing return in between). When you are finish, respond: 'DONE'.\n"
			response = get_multi_interactive(prompt, format_str='%s')
		elif self.input_type == 'synthetic':
			possible_symptoms = self.get_possible_symptoms()
			n_new = get_random_answer(np.arange(1,4))
			response = list(np.random.choice(possible_symptoms, n_new))
		else:
			response = self.canned['Symptoms']
		#
		curr_time = cm_medical_info.get_current_time()
		cm_medical_info.symptom_list = response
		results = ["\n%s Began experiencing %s." % (curr_time, result) for result in response]
		cm_medical_info.cm_info_dict['EHRS'] = cm_medical_info.cm_info_dict['EHRS']+''.join(results)
		return cm_medical_info
	#
	def load_patient_history(self, test_dir, cm_medical_info):
		response = []
		if self.input_type == 'interactive':
			prompt = "Please input your medical history. When you are finish, respond: 'DONE'.\n"
			response = '\n'+'\n'.join(get_multi_interactive(prompt, format_str='%s'))
		elif self.input_type == 'synthetic':
			disease = np.random.choice(canned_options, 1)[0]
			disease_dict = json.loads(load_inputs('%s/canned/%s.json' % (test_dir, disease)))
			response = disease_dict['EHR']
		else:
			response = self.canned['EHR']
		cm_medical_info.cm_info_dict['EHRS'] = response
		return cm_medical_info
	#
	def get_possible_symptoms(self):
		query = "MATCH (n:Symptom) RETURN DISTINCT n.name as i"
		symptoms = list(self.kg.run_cypher(query).i.unique())
		return symptoms
	#
	def run_survey(self, cm_medical_info, test_dir):
		survey_answers = []
		if (self.input_type == 'interactive') or (self.input_type == 'synthetic'):
			survey_questions = load_inputs(test_dir+'/pain_survey').strip().split('\n')
			survey_template_dict = json.loads(load_inputs(test_dir+'/survey_response_template'))
			survey_answers, answer = [], ''
			for question in survey_questions:
				answer = input(question+'\n') if self.input_type == 'interactive' else get_random_from_question(question)
				try:
					answer = float(answer)
					survey_answers.append(survey_template_dict[question][str(answer>0)] % answer)
				except ValueError:
					survey_answers.append(survey_template_dict[question][answer])
		else:
			survey_answers = self.canned['pain_survey']
		#
		curr_time = cm_medical_info.get_current_time()
		results = ["%s %s" % (curr_time, result) for result in survey_answers if len(result)>0]
		cm_medical_info.cm_info_dict['PAIN SURVEY'] = '\n'+'\n'.join(results)
		return cm_medical_info


def get_multi_interactive(prompt, format_str='%s'):
	answer = 'start'
	response = []
	while answer.upper() != 'DONE':
		answer = input(prompt)
		if answer.upper() != 'DONE':
			response.append(format_str % answer)
	return response


def get_random_from_question(question):
	answer = re.findall(r'[0-9]+|Y|N|one|both', question.split('Respond: ')[1])
	try:
		answer = np.array(answer, dtype=int)
		answer = get_random_answer(np.arange(answer[0], answer[1]))
	except ValueError:
		answer = get_random_answer(answer)
	return answer

def get_random_answer(choices):
	return np.random.choice(choices, 1)[0]

def load_inputs(filename):
	text = ''
	with open(filename, 'r') as file:
		text = ''.join(file.readlines()).strip()
	return text





def make_kg_actions_and_nt_embeddings(kg, test_dir, all_possible_actions, early_tests, monitor_actions):
	#create_vectordb('tests/'+test_dir, 'kg_action_options')
	#create_vectordb('tests/'+test_dir, 'emergency_stage_options')
	kg_action_options = addl_action_list+early_tests+monitor_actions+end_differential_actions+end_initial_assessment_actions
	kg_action_options = np.union1d(all_possible_actions, kg_action_options)
	with open('tests/%s/kg_action_options' % test_dir, 'w') as out:
		out.write('\n'.join(kg_action_options))
	create_vectordb('tests/'+test_dir, 'kg_action_options')
	#
	nt_list = ['Condition', 'Symptom', 'Disease', 'MedKit']
	for nt in nt_list:
		name_list = kg.run_cypher("MATCH (n:%s) RETURN DISTINCT n.name as n" % nt).n.unique()
		print(name_list.shape)
		with open('tests/%s/%s' % (test_dir, nt), 'w') as out:
			out.write('\n'.join(name_list))
		create_vectordb('tests/'+test_dir, nt)



