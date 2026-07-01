import pandas as pd
import streamlit as st
from random import randint
import random
import string
from ..functions.color import *
import os
import requests

from ..functions.gui import (
	get_html_text,
	get_neighbor_path,
	get_mode_and_input_type,
	get_use_case_narrative,
	get_current_stage_tab,
	get_emergency_history_tab,
	get_possible_diag_tab,
	get_rx_tab,
	random_token,
)


#from ..functions.gui import options_to_continue,get_start_ehr_token


from PIL import Image
from ..functions.path import pages_str, data_str, get_file_path, load_json, save_json
import numpy as np

from ..functions.query_mdm import get_mdm_next_step, get_interactive_mdm_next_step


"""

************ INITIAL SYMPTOMS IS PULLING FROM CANNED ***************


END Button actually goes to next stage but when you press it next seems to disappear which is good
	Probably need to put the save session in button def
Time doesnt seem to be adding much? Add time for pain survey...
The diagnosis section isnt recognizing all diseases for some reason
For some reason disease was removed after confirmed


set all interactive up then just print results on api side

works except for first

************ Need to fix ************
Remove session json


************ Nice to fix ************
Add spinner to interactive
Clean up narrative text
"""


def use_case_3():
	use_case = 'use_case_1'
	canned_data = 'Pneumothorax.json'
	#
	session_file = '%s/%s/session.json' % (get_neighbor_path(__file__, pages_str, data_str), use_case)
	session_dict = load_json(session_file)
	get_start_ehr_token()
	print(st.session_state["prev_stage"], st.session_state["ehr_token"])
	#
	# EHR SIDEBAR
	ehr_dict = load_json('%s/%s/ehr.json' % (get_neighbor_path(__file__, pages_str, data_str), use_case))
	headshot = Image.open(
		get_file_path(
			"%s/headshot.png" % use_case,
			dir_path=get_neighbor_path(__file__, pages_str, data_str),
		)
	)
	st.sidebar.image(headshot, output_format="PNG")
	st.sidebar.markdown(f"#### {ehr_dict['Name']}")
	#
	info_cols = ["Age", "Sex", "Race/Ethnicity", "History"]
	for col in info_cols:
		st.sidebar.markdown(f"**{col}:** {ehr_dict[col]}")
	#
	#mode_selection = st.sidebar.selectbox("Mode", ['Canned EHRs', 'Synthetic EHRs', 'Interactive'])
	### need to keep as canned for now it loads something
	session_dict, input_type = get_mode_and_input_type('Canned EHRs', session_dict, canned_data)
	#
	# END EHR SIDEBAR
	# 
	ehr_dict = load_json('%s/%s/ehr.json' % (get_neighbor_path(__file__, pages_str, data_str), use_case))
	#
	#
	#
	if "submitted" not in st.session_state:
		print('adding submitted to session_state')
		st.session_state["submitted"] = False
	#
	if "response_dict" not in st.session_state:
		print('adding response_dict to session_state')
		st.session_state["response_dict"] = {}
	#
	#
	# Get next step
	### make seperate pages for input
	input_stages =  ["Start", "Initial Assessment Stage", "Differential Diagnosis Stage", "Monitoring Stage"]
	skip_monitor = ['Reassess crew member status in 30 minutes.', 'Reassess crew member status in 24 hours.', 'Reassess crew member status in 1 hour.']
	#
	if (st.session_state["prev_stage"] in input_stages) and (st.session_state.submitted == False):
		full_tab_titles = ["Next Stage", "Emergency History", "Diagnoses", "Interventions", "Use Case Narrative"]
		first_tab_titles = ["Use Case Narrative", "Next Stage"]
		tabs = st.tabs(full_tab_titles) if len(st.session_state.response_dict) > 0 else st.tabs(first_tab_titles)
		narrative_index = 4 if len(st.session_state.response_dict) > 0 else 0
		get_use_case_narrative(use_case, tabs[narrative_index], st.session_state["prev_stage"])
		#
		# get input
		#
		print(st.session_state["prev_stage"], 'getting input')
		#
		input_response = []
		st.session_state["prompts"] = get_input_prompt(st.session_state.response_dict, use_case) 
		with st.form('Input:'):
			# probably going to return an action string
			for i, prompt in enumerate(st.session_state["prompts"]):
				input_response.append(st.text_input(label=prompt, on_change=None, key=f'input_{i}'))
			submit = st.form_submit_button(label='Submit', on_click=get_user_input)
		#
	else:
		full_tab_titles = ["Next Stage", "Emergency History", "Diagnoses", "Interventions", "Use Case Narrative"]
		tabs = st.tabs(full_tab_titles)
		get_use_case_narrative(use_case, tabs[4], st.session_state["prev_stage"])
		#
		print('current input', st.session_state["user_input"])
		print(st.session_state["prev_stage"], 'getting respose')
		# press submit does it have input?
		#
		new_stage = st.session_state["prev_stage"] if len(st.session_state.response_dict)==0 else st.session_state.response_dict["new_stage"]
		next_test = 'next' if len(st.session_state.response_dict)==0 else st.session_state.response_dict["next_test"]
		st.session_state.response_dict = get_interactive_mdm_next_step(st.session_state["ehr_token"], 'interactive', 
			new_stage, st.session_state["user_input"], next_test)
		if st.session_state["prev_stage"] == "Diagnosis Stage":
			st.session_state["high_severity_diag"] = st.session_state.response_dict["high_severity_diag"]
			st.session_state["low_severity_diag"] = st.session_state.response_dict["low_severity_diag"]
		elif st.session_state["prev_stage"] == "Differential Diagnosis Stage":
			st.session_state.response_dict["high_severity_diag"] = list(set(st.session_state["high_severity_diag"])-set(st.session_state.response_dict["eliminated_diag"]))
			st.session_state.response_dict["low_severity_diag"] = list(set(st.session_state["low_severity_diag"])-set(st.session_state.response_dict["eliminated_diag"]))

		#print(st.session_state.response_dict)
		print(st.session_state.response_dict["next_test"])
		#
		st.session_state["prev_stage"] = st.session_state.response_dict["new_stage"]
		# reset submit
		options_to_continue()
		#save_json(session_file, session_dict)
		st.session_state["user_input"] = []
		reset()
	#
	show_tabs(tabs)
	#save_json(session_file, session_dict)


def get_start_ehr_token():
	if "ehr_token" not in st.session_state:
		st.session_state["ehr_token"] = random_token()
		st.session_state["prev_stage"] = "Start"
		st.session_state.response_dict = {}

def options_to_continue():
	st.markdown("### Continue Scenario:")
	next_option_buttons = [
		"Restart",
		"End",
		"Next",
	]
	next_option_buttons_help = [
		"Restart use case.",
		"End use case.",
		"Move to next stage.",
	]
	# horizontal_alignment?
	st.markdown("If you would like to continue with this use case, please click Next. Otherwise, you can restart or end the use case.")
	button_cols = st.columns(3)
	button_pressed = ""
	if button_cols[0].button(next_option_buttons[0], help=next_option_buttons_help[0], on_click=restart_page):
		button_pressed = next_option_buttons[0]
		st.session_state["ehr_token"] = random_token()
		st.session_state["prev_stage"] = "Start"
		st.session_state.response_dict = {}
		st.session_state["submitted"] = False
	elif button_cols[1].button(next_option_buttons[1], help=next_option_buttons_help[1]):
		button_pressed = next_option_buttons[1]
		st.session_state["prev_stage"] = "Stable Health Stage"
	elif button_cols[2].button(next_option_buttons[2], help=next_option_buttons_help[2]):
		button_pressed = next_option_buttons[2]


def restart_page():
	for key in st.session_state.keys():
		del st.session_state[key]

def show_tabs(tabs):
	#
	if len(st.session_state.response_dict) > 0:
		# CURRENT STAGE MAIN SECTION
		st.session_state["prev_stage"] = get_current_stage_tab(st.session_state.response_dict, tabs[0])
		#
		# EMERGENCY HISTORY MAIN SECTION
		get_emergency_history_tab(tabs[1], st.session_state.response_dict)
		#
		# Possible diag
		get_possible_diag_tab(st.session_state.response_dict, tabs[2])
		#
		# Rx tab
		get_rx_tab(st.session_state.response_dict, tabs[3])
		if st.session_state["prev_stage"] not in ['Diagnosis Stage', 'Intervention Stage', "Stable Health Stage"]:
			st.session_state["getting_input"] = True



def get_user_input():
	if (len(st.session_state.response_dict)>0) and (st.session_state.response_dict['next_test'] == "Reassess crew member's symptoms."):
		st.session_state["user_input"] = {"check":[]}
		for i, prompt in enumerate(st.session_state["prompts"][:-1]):
			st.session_state["user_input"]["check"].append(st.session_state[f"input_{i}"])
		print(st.session_state["prompts"])
		n_reassess = int(len(st.session_state["prompts"])-1)
		symptoms = st.session_state[f"input_{n_reassess}"]
		symptoms = [symptom.strip() for symptom in symptoms.split(',')]
		print(symptoms)
		if len(symptoms)>0:
			st.session_state["user_input"]["has_new"] = "Y"
			st.session_state["user_input"]["new"] = symptoms
	elif (len(st.session_state.response_dict)>0) and (st.session_state.response_dict['next_test'] == "Reassess crew member's vitals."):
		st.session_state["user_input"] = {}
		for i, prompt in enumerate(st.session_state["prompts"]):
			prompt = prompt[17:-9]
			st.session_state["user_input"][prompt] = st.session_state[f"input_{i}"]
	else:
		st.session_state["user_input"] = []
		for i, prompt in enumerate(st.session_state["prompts"]):
			st.session_state["user_input"].append(st.session_state[f"input_{i}"])
	st.session_state.submitted = True


def get_input_prompt(response_dict, use_case):
	prompt = []
	if 'new_stage' not in st.session_state.response_dict:
		# new stage comes after start
		filename = get_file_path("%s/pain_survey" % use_case, dir_path=get_neighbor_path(__file__, pages_str, data_str),)
		with open(filename, 'r') as pain_survey:
			prompt = [lines.strip() for lines in pain_survey.readlines()]
	else:
		if "prompt" in st.session_state.response_dict["prompt_dict"]:
			#prompt = [f'Please enter the results for {st.session_state.response_dict["next_test"]}']
			prompt = st.session_state.response_dict["prompt_dict"]["prompt"]
		elif st.session_state.response_dict['next_test'] == "Reassess crew member's symptoms.":
			prompt = st.session_state.response_dict["prompt_dict"]["check"]
			prompt += [st.session_state.response_dict["prompt_dict"]["new"]]
	return prompt




def interactive_options_to_continue(response_dict, use_case, input_func):
	st.markdown("### Continue Scenario:")
	st.markdown("If you would like to continue with this use case, please fill out the input form and press *Submit*. Otherwise, you can *Restart* or *End* the use case.")
	next_option_buttons = [
		"Restart",
		"End",
	]
	next_option_buttons_help = [
		"Restart use case.",
		"End use case.",
	]
	st.session_state["getting_input"] = True
	get_input_container(st.session_state.response_dict, use_case, input_func)
	# horizontal_alignment?
	button_cols = st.columns(2)
	button_pressed = ""
	if button_cols[0].button(next_option_buttons[0], help=next_option_buttons_help[0]):
		button_pressed = next_option_buttons[0]
		st.session_state["ehr_token"] = ""
		st.session_state["prev_stage"] = "Start"
	elif button_cols[1].button(next_option_buttons[1], help=next_option_buttons_help[1]):
		button_pressed = next_option_buttons[1]
		st.session_state["prev_stage"] = "Stable Health Stage"


def get_input_container(response_dict, use_case, input_func):
	#
	if "getting_input" not in st.session_state:
		st.session_state["getting_input"] = True
	#
	input_response = input_func(st.session_state.response_dict, use_case)
	



def submitted():
	st.session_state.submitted = True

def reset():
	st.session_state.submitted = False


