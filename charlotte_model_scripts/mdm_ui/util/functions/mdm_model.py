from ollama_llm import OllamaCustomLLMforEval
from compare_models import load_test_inputs, Answer, run_with_langchain
from evaluate_llm import run_all_eval, run_all_eval_with_gpt3
from bulk_evaluate_llm import run_bulk_eval
import pandas as pd
import time
import numpy as np
from langchain import PromptTemplate
import json
import re
import os
from datetime import datetime, timedelta
from health_record import MedicalInformation
import pickle
import subprocess

from get_kg_actions import KGActionStore, open_gds, test_dir
from get_kg_actions import addl_action_list, end_differential_actions, end_initial_assessment_actions
from get_kg_actions import actions_vectorstore
from get_kg_context import get_action_phrase_to_name, get_actions_of_diseases, get_diseases_of_symptoms, early_diagnosis_context, get_rx_context, get_diagnosis_context

from health_record import MedicalInformation
from get_kg_actions import KGActionStore, open_gds


#clinical_background_type = 'medical_llm'
#medical_model_name = 'medllama2'
clinical_background_type = 'exmc_kg'
DISEASE_SIMILARITY_FILTER = 0.7

canned_directory = "tests/interactive_assessment/canned/"

### get actions
monitor_limit = 4
#

input_directory = 'tests/interactive_assessment/inputs/v2/'
instruction_directory = input_directory+'instructions/'
prompt_directory = input_directory+'prompts/'
question_directory = input_directory+'questions/'


def get_stage_response(current_model, input_type, ehr_token, new_stage = 'Initial Assessment Stage'):	
	# Load EHR data if model run
	cm_medical_info, action_store = load_medical_info_and_action_store(current_model, input_type, ehr_token)	
	cm_medical_info.seen_stages.append('%s %s'% (cm_medical_info.get_current_time(), new_stage))
	#
	print(new_stage)
	if new_stage == 'Initial Assessment Stage':
		cm_medical_info = make_initial_assesement(current_model, cm_medical_info, cm_medical_info.potential_disease_str, action_store)
	elif new_stage == 'Diagnosis Stage':
		cm_medical_info = get_diagnosis(current_model, cm_medical_info, action_store)
	elif new_stage == 'Differential Diagnosis Stage':
		cm_medical_info = get_differential_diagnosis(current_model, cm_medical_info, action_store)
	elif new_stage == 'Intervention Stage':
		cm_medical_info = get_rx(current_model, cm_medical_info, action_store)
	elif new_stage =='Monitoring Stage':
		cm_medical_info = monitor_crew_member(current_model, cm_medical_info, action_store)
	elif new_stage =='Stop':
		new_stage = 'Stable Health Stage'
		print('done', new_stage)
	#
	# check if too many monitor
	if len([stage for stage in cm_medical_info.seen_stages if 'Monitoring Stage' in stage])>=monitor_limit:
		new_stage = 'Stable Health Stage'
	#
	# get next stage
	if new_stage != 'Stable Health Stage':
		new_stage = get_emergency_stage(current_model, cm_medical_info)
		cm_medical_info.seen_stages.append('%s %s'% (cm_medical_info.get_current_time(), new_stage))
		# assume stable if number of monitoring statements over the limit
	#
	if new_stage == 'Stable Health Stage':
		subprocess.call('rm stored_ehrs/%s.pkl' % ehr_token, shell=True)
	else:
		store_medical_info(cm_medical_info, ehr_token)
	return cm_medical_info, new_stage

def load_medical_info_and_action_store(current_model, input_type, ehr_token):
	#input_type = 'Pneumothorax.json'
	#input_type = 'synthetic' 
	#input_type = 'interactive'
	input_type = canned_directory+input_type if input_type not in ['interactive', 'synthetic'] else input_type
	action_store = KGActionStore(input_type)
	cm_medical_info = None
	if os.path.exists('stored_ehrs/%s.pkl' % ehr_token):
		with open('stored_ehrs/%s.pkl' % ehr_token, 'rb') as f:
		    cm_medical_info = pickle.load(f)
	else:
		cm_medical_info = MedicalInformation('Crew Member 1')
		cm_medical_info = action_store.get_initial_interaction('tests/'+test_dir, cm_medical_info)
		output, is_severe, potential_disease_str, cm_medical_info = decide_severity(current_model, cm_medical_info, action_store)
		cm_medical_info.potential_disease_str = potential_disease_str
	return cm_medical_info, action_store

def store_medical_info(cm_medical_info, ehr_token):
	with open('stored_ehrs/%s.pkl' % ehr_token, 'wb') as f:
		pickle.dump(cm_medical_info, f)

def decide_severity(current_model, cm_medical_info, action_store):
	med_emergency = 'Crew member is experiencing the following symptoms: %s.' % ', '.join(cm_medical_info.symptom_list)
	cm_medical_info, potential_disease_str = get_diseases_of_symptoms(action_store.kg, cm_medical_info)
	current_model, question = load_cm_inputs(current_model, cm_medical_info, 'decide_severity')
	if clinical_background_type == 'exmc_kg':
		med_emergency = '\n'.join([med_emergency, potential_disease_str])
	input_dict = {'context':load_tests('tests/%s/' % test_dir, 'symptoms_context'), 'health_status':med_emergency}
	output = current_model.get_llm_output(input_dict, input_variables=["context", "health_status"])
	is_severe = False
	if 'YES' in output.upper():
		is_severe = True
	return output, is_severe, potential_disease_str, cm_medical_info

def make_initial_assesement(current_model, cm_medical_info, potential_disease_str, action_store):
	next_step = ''
	early_tests = list(action_store.kg.run_cypher("MATCH (n:Action {early_action:true}) RETURN DISTINCT n.phrase as n").n.unique())
	possible_actions = early_tests+end_initial_assessment_actions
	while next_step not in end_initial_assessment_actions:
		possible_actions = list(set(possible_actions)-set(cm_medical_info.seen_actions))
		if len(possible_actions) > 0:
			action_str = get_actions_of_diseases(action_store.kg, cm_medical_info.early_diseases, possible_actions)
			action_str = potential_disease_str if action_str == '' else '\n'.join([potential_disease_str])
			next_step = get_next_step(current_model, cm_medical_info, format_actions(possible_actions), potential_disease_str)
			print(action_str)
			next_step = actions_vectorstore['kg_action_options'].similarity_search_with_score(next_step, k=1)[0][0].page_content
			if next_step not in end_initial_assessment_actions:
				cm_medical_info.seen_actions+=[next_step]
				next_step = get_action_phrase_to_name(next_step, action_store.kg)
				cm_medical_info = action_store.get_results(cm_medical_info, next_step)
	return cm_medical_info

def get_emergency_stage(current_model, cm_medical_info):
	med_info = '\n'.join([cm_medical_info.get_medical_infomation(), cm_medical_info.get_probable_diag_information()])
	emergency_stages = load_tests('tests/%s/' % test_dir, 'emergency_stages').strip()
	previous_stages = '\nPrevious Emergency Stages:\n%s\n' % '\n'.join(cm_medical_info.seen_stages)
	context = "%s\n%s\n%s\n" % (emergency_stages, previous_stages, med_info)
	#print("%s\n%s\n" % (previous_stages, med_info))
	#
	current_model, question = load_cm_inputs(current_model, cm_medical_info, 'get_emergency_stage')
	input_dict = {'context':context, 'question': question}
	output = current_model.get_llm_output(input_dict, input_variables=["context", "question"])
	output = actions_vectorstore['emergency_stage_options'].similarity_search_with_score(output, k=1)[0][0].page_content
	return output

def get_next_step(current_model, cm_medical_info, action_options, kg_context=''):
	med_context = cm_medical_info.get_medical_infomation()
	if (clinical_background_type == 'exmc_kg') and (kg_context !=''):
		med_context = '\n'.join([med_context.strip(), kg_context])+'\n\n'
	context = "%sACTION OPTIONS:%s\n" % (med_context, action_options)
	current_model, question = load_cm_inputs(current_model, cm_medical_info, 'get_next_step')
	input_dict = {'context':context, 'question':question}
	output = current_model.get_llm_output(input_dict, input_variables=["context", "question"])
	return output

def format_actions(action_list):
	action_options = '\n'.join([action for i, action in enumerate(action_list)])
	return action_options

def get_diagnosis(current_model, cm_medical_info, action_store):
	diagnoses = get_probable_diagnoses(current_model, cm_medical_info, action_store)
	diagnoses = '\n'+''.join(re.split(r'[0-9]+\. ', diagnoses))
	#diagnoses = clean_diagnoses_w_astrisk(diagnoses)
	diagnoses_df = get_df_from_results(get_rank_diagnoses(current_model, cm_medical_info, diagnoses))
	diagnoses_df.loc[:,'Diagnosis Rank'] = diagnoses_df['Diagnosis Rank'].values.astype(int)
	diagnoses_df.loc[:,'Diagnosis Severity Label'] = [check_diagnosis_severity(current_model, cm_medical_info, diagnosis).strip().upper() for diagnosis in diagnoses_df.Diagnosis.values]
	diagnoses_df = diagnoses_df.sort_values('Diagnosis Rank')
	diagnoses_df.loc[:,'Rank_By_Severity'] = diagnoses_df.groupby('Diagnosis Severity Label').cumcount(ascending=True).values + 1
	#
	cm_medical_info.high_severity_diag += list(diagnoses_df[diagnoses_df['Diagnosis Severity Label']=='HIGH'].Diagnosis.values)
	print(cm_medical_info.high_severity_diag)
	cm_medical_info.low_severity_diag += list(diagnoses_df[diagnoses_df['Diagnosis Severity Label']=='LOW'].Diagnosis.values)
	print(cm_medical_info.low_severity_diag)
	cm_medical_info.early_diseases = check_pheno_match(cm_medical_info.high_severity_diag+cm_medical_info.low_severity_diag)
	return cm_medical_info


def clean_diagnoses_w_astrisk(diagnoses):
	bad_diag_pattern = re.compile('Probable|Possible|Important Considerations|Trauma Details|Physical Exam|Medical Professional Required|Further Assessment is Necessary|Important Notes|Further', re.IGNORECASE)
	if '**' in diagnoses:
		new_diag = []
		for line in diagnoses.strip().split('\n'):
			if (len(bad_diag_pattern.findall(line))==0) and ('**' in line):
				new_diag.append(line.split('**')[-2].strip(':| '))
		diagnoses = '\n%s\n'%'\n'.join(new_diag)
		print(diagnoses)
	return diagnoses


def check_pheno_match(pheno_list):
	match_list = []
	for original_pheno in pheno_list:
		for nt in ['Symptom', 'Disease']:
			pheno, score = actions_vectorstore[nt].similarity_search_with_score(original_pheno, k=1)[0]
			pheno = pheno.page_content
			print(original_pheno, pheno, score )
			if (pheno != '') and (score < DISEASE_SIMILARITY_FILTER):
				match_list.append(pheno)
	match_list = sorted(set(match_list))
	return match_list


def get_probable_diagnoses(current_model, cm_medical_info, action_store):
	context = '\n'.join([cm_medical_info.get_medical_infomation(), cm_medical_info.get_probable_diag_information()])
	context += get_clinical_background('prelim_get_probable_diagnoses', context, cm_medical_info, action_store)
	current_model, question = load_cm_inputs(current_model, cm_medical_info, 'get_probable_diagnoses')
	input_dict = {'context':context, 'question':question}
	output = current_model.get_llm_output(input_dict, input_variables=["context", "question"])
	return output

def get_clinical_background(test_type, context, cm_medical_info, action_store):
	clinical_context = ''
	if clinical_background_type == 'exmc_kg':
		if test_type == 'prelim_get_probable_diagnoses':
			clinical_context = '\nClinical Background:\n%s' % early_diagnosis_context(action_store.kg, cm_medical_info)
		elif test_type == 'prelim_next_step_for_differential':
			action_filter = 'NOT a.phrase IS NULL AND NOT a.phrase IN %s' % cm_medical_info.seen_actions
			clinical_context = '\nClinical Background:\n%s' % get_diagnosis_context(action_store.kg, cm_medical_info, '', action_filter)
		elif test_type == 'prelim_get_rx':
			clinical_context = '\nClinical Background:\n%s' % get_rx_context(action_store.kg, cm_medical_info)
	elif clinical_background_type == 'medical_llm':
		print('in medical llm')
		medical_model = OllamaCustomLLMforEval(medical_model_name)
		medical_model, question = load_cm_inputs(medical_model, cm_medical_info, test_type)
		input_dict = {'context':context, 'question':question}
		output = current_model.get_llm_output(input_dict, input_variables=["context", "question"])
		clinical_context = '\nClinical Background:\n%s' % output
	return clinical_context

def get_df_from_results(output):
	# only works for formating 2 col df with number col last
	df = [row.strip().replace('```', '').split('\t') for row in output.strip().split('\n')]
	columns, df = df[0], df[1:]
	print(columns, df)
	if len(df[0])!= len(columns):
		for i, row in enumerate(df):
			row = '\t'.join(row)+'\n'
			seen = re.search(r'[ ,]+[0-9]+\n', row)
			df[i] = [row[:seen.span()[0]], re.search(r'[0-9]+', seen.group().strip()).group()]
	df = pd.DataFrame(df, columns=columns)
	return df

def get_rank_diagnoses(current_model, cm_medical_info, diagnoses):
	current_model, question = load_cm_inputs(current_model, cm_medical_info, 'get_rank_diagnoses')
	input_dict = {'context':cm_medical_info.get_medical_infomation(), 'diagnoses':diagnoses}
	output = current_model.get_llm_output(input_dict, input_variables=["context", "diagnoses"])
	return output

def check_diagnosis_severity(current_model, cm_medical_info, diagnosis):
	current_model, question = load_cm_inputs(current_model, cm_medical_info, 'check_diagnosis_severity')
	input_dict = {'context':cm_medical_info.get_medical_infomation(), 'diagnosis':diagnosis}
	output = current_model.get_llm_output(input_dict, input_variables=["context", "diagnosis"])
	return output

def get_differential_diagnosis(current_model, cm_medical_info, action_store):
	### differential has access to all unused DIAGNOSES_AdC until we filter
	#action_option_list = list(np.setdiff1d(all_possible_actions, cm_medical_info.seen_actions))
	#action_option_list = action_option_list+end_differential_actions
	all_possible_actions = action_store.kg.run_cypher("MATCH (n:Action {is_action:true}) WHERE NOT n.phrase IS NULL RETURN DISTINCT n.phrase as n").n.unique()
	new_stage = False
	confirmed_diseases = []
	while new_stage == False:
		action_option_list = list(np.setdiff1d(all_possible_actions, cm_medical_info.seen_actions))
		action_option_list = action_option_list+end_differential_actions
		current_diagnoses = '\n'.join(cm_medical_info.high_severity_diag)
		if len(current_diagnoses) == 0:
			current_diagnoses = '\n'.join(cm_medical_info.low_severity_diag)
		next_step = next_step_for_differential(current_model, cm_medical_info, action_option_list, current_diagnoses, action_store)
		next_step = actions_vectorstore['kg_action_options'].similarity_search_with_score(next_step, k=1)[0][0].page_content
		if next_step in all_possible_actions:
			cm_medical_info.seen_actions+=[next_step]
			next_step = get_action_phrase_to_name(next_step, action_store.kg)
			cm_medical_info = action_store.get_results(cm_medical_info, next_step)
			cm_medical_info = update_diagnosis_list(current_model, cm_medical_info, next_step, cm_medical_info.high_severity_diag, 'HIGH')
			cm_medical_info = update_diagnosis_list(current_model, cm_medical_info, next_step, cm_medical_info.low_severity_diag, 'LOW')
			if len(cm_medical_info.high_severity_diag)==0:
				new_stage = True
			elif len(cm_medical_info.high_severity_diag+cm_medical_info.low_severity_diag) == 0:
				print('all diseases eliminated')
				new_stage = True
			#
		elif next_step == "Nothing more to do.":
			new_stage = True
		else:
			print('else')
			new_stage = True
	action_option_list = action_option_list+["Reassess crew member status in 30 minutes.", "Diagnose crew member.", "Prescribe medication."]
	return cm_medical_info

def next_step_for_differential(current_model, cm_medical_info, action_options, diagnoses, action_store):
	context = "%sPOSSIBLE DIAGNOSES:%s\n" % (cm_medical_info.get_medical_infomation(), diagnoses)
	context += get_clinical_background('prelim_next_step_for_differential', context, cm_medical_info, action_store)
	context += "ACTION OPTIONS:%s\n" % action_options
	#
	current_model, question = load_cm_inputs(current_model, cm_medical_info, 'next_step_for_differential')
	input_dict = {'context':context, 'question':question}
	output = current_model.get_llm_output(input_dict, input_variables=["context", "question"])
	return output

def update_diagnosis_list(current_model, cm_medical_info, next_step, diag_list, high_or_low):
	updated_list = []
	for diagnosis in diag_list:
		status = single_differential_interpretation(current_model, cm_medical_info, next_step, diagnosis)
		if status == 'ELIMINATED':
			cm_medical_info.eliminated_diag += [diagnosis]
			print('eliminated', diagnosis)
		elif status == 'CONFIRMED':
			confirmed_str = "\n%s Confirmed diagnosis: %s"
			confirmed_str = confirmed_str % (cm_medical_info.get_current_time(), diagnosis)
			print('in confirmed', confirmed_str)
			cm_medical_info.cm_info_dict['EHRS'] = cm_medical_info.cm_info_dict['EHRS']+confirmed_str
		else:
			updated_list.append(diagnosis)
	if high_or_low == 'HIGH':
		cm_medical_info.high_severity_diag = updated_list
	else:
		cm_medical_info.low_severity_diag = updated_list
	return cm_medical_info

def single_differential_interpretation(current_model, cm_medical_info, last_action, diagnoses):
	context = "%sPOSSIBLE DIAGNOSIS:%s\nLATEST ACTION:%s\n" % (cm_medical_info.get_medical_infomation(), diagnoses, last_action)
	current_model, question = load_cm_inputs(current_model, cm_medical_info, 'single_differential_interpretation')
	input_dict = {'context':context, 'question':question}
	output = current_model.get_llm_output(input_dict, input_variables=["context", "question"])
	update_pattern = re.compile(r'Confirmed|Eliminated|Unchanged|Confirmation|Elimination', re.IGNORECASE)
	output = ''.join(update_pattern.findall(output)).upper().replace('ELIMINATION','ELIMINATED').replace('CONFIRMATION', 'CONFIRMED')
	return output

def get_rx(current_model, cm_medical_info, action_store):
	context = cm_medical_info.get_medical_infomation()
	context += get_clinical_background('prelim_get_rx', context, cm_medical_info, action_store)
	current_model, question = load_cm_inputs(current_model, cm_medical_info, 'get_rx')
	input_dict = {'context':context, 'question':question}
	output = current_model.get_llm_output(input_dict, input_variables=["context", "question"])
	for rx in output.strip().split('\n')[1:]:
		cm_medical_info.rx_list.append('%s %s' % (cm_medical_info.get_current_time(), rx))
	print(cm_medical_info.rx_list)
	return cm_medical_info

def monitor_crew_member(current_model, cm_medical_info, action_store):
	monitor_actions = list(action_store.kg.run_cypher("MATCH (n:Action {general_monitor:true}) RETURN DISTINCT n.name as n").n.unique())
	#possible_actions = list(set(monitor_actions)-set(cm_medical_info.seen_actions))
	possible_actions = list(set(monitor_actions))
	if 'Monitoring Stage' in cm_medical_info.seen_stages[-1]:
		possible_actions = list(set(monitor_actions)-set(cm_medical_info.seen_actions))
	next_step = get_next_step(current_model, cm_medical_info, format_actions(possible_actions))
	next_step = actions_vectorstore['kg_action_options'].similarity_search_with_score(next_step, k=1)[0][0].page_content
	cm_medical_info.seen_actions+=[next_step]
	cm_medical_info = action_store.get_results(cm_medical_info, next_step)
	return cm_medical_info

def load_cm_inputs(current_model, cm_medical_info, test_type):	
	read_info = cm_medical_info.get_medical_sections()
	use_read_info = json.loads(load_tests(input_directory, 'use_read_info.json'))
	#
	prompt = load_tests(prompt_directory, test_type)
	instruction = load_tests(instruction_directory, test_type)
	if use_read_info['prompt'][test_type] == True:
		prompt = prompt % read_info
	current_model.set_template(instruction, prompt)
	#
	question = load_tests(question_directory, test_type) if os.path.exists(question_directory+test_type) else ''
	if use_read_info['question'][test_type] == True:
		question = question % read_info
	return current_model, question


def load_tests(test_dir, file_type):
	text = ''
	with open('%s%s' % (test_dir, file_type), 'r') as file:
		text = ''.join(file.readlines())
	return text




