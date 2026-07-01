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
	get_start_ehr_token, 
	get_mode_and_input_type,
	get_use_case_narrative,
	get_current_stage_tab,
	get_emergency_history_tab,
	get_possible_diag_tab,
	get_rx_tab,
	options_to_continue,
)




from PIL import Image
from ..functions.path import pages_str, data_str, get_file_path, load_json, save_json
import numpy as np

from ..functions.query_mdm import get_mdm_next_step


"""
END Button actually goes to next stage but when you press it next seems to disappear which is good
	Probably need to put the save session in button def
Time doesnt seem to be adding much? Add time for pain survey...
The diagnosis section isnt recognizing all diseases for some reason
For some reason disease was removed after confirmed


set all interactive up then just print results on api side

"""


def use_case_1():
	use_case = 'use_case_1'
	canned_data = 'Pneumothorax.json'
	#
	session_file = '%s/%s/session.json' % (get_neighbor_path(__file__, pages_str, data_str), use_case)
	session_dict = load_json(session_file)
	session_dict = get_start_ehr_token(session_dict)
	print(session_dict["prev_stage"], session_dict["ehr_token"])
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
	session_dict, input_type = get_mode_and_input_type('Canned EHRs', session_dict, canned_data)
	#
	# END EHR SIDEBAR
	# 
	ehr_dict = load_json('%s/%s/ehr.json' % (get_neighbor_path(__file__, pages_str, data_str), use_case))
	#
	#
	#
	#
	# Put a cap on diff diag that we will need to fix
	#
	#
	full_tab_titles = ["Next Stage", "Emergency History", "Diagnoses", "Interventions", "Use Case Narrative"]
	first_tab_titles = ["Use Case Narrative", "Next Stage", "Emergency History"]
	tabs = st.tabs(full_tab_titles) if session_dict["first_step"]==False else st.tabs(first_tab_titles)
	#
	if session_dict["first_step"] == False:
		# Use Narrative Tab
		get_use_case_narrative(use_case, tabs[4], session_dict["prev_stage"])
		#
		response_dict = {}
		with st.spinner(text="Running %s" % session_dict["prev_stage"][:-6]):
			response_dict = get_mdm_next_step(session_dict, input_type)
		#
		# CURRENT STAGE MAIN SECTION
		session_dict["prev_stage"] = get_current_stage_tab(response_dict, tabs[0])
		#
		# EMERGENCY HISTORY MAIN SECTION
		get_emergency_history_tab(tabs[1], response_dict)
		#
		# Possible diag
		get_possible_diag_tab(response_dict, tabs[2])
		#
		# Rx tab
		get_rx_tab(response_dict, tabs[3])
		#
	else:
		# Only Narrative
		get_use_case_narrative(use_case, tabs[0], session_dict["prev_stage"])
		#
		response_dict = get_mdm_next_step(session_dict, input_type)
		#
		# CURRENT STAGE MAIN SECTION
		session_dict["prev_stage"] = get_current_stage_tab(response_dict, tabs[1])		#
		session_dict["first_step"] = False
		#
		# EMERGENCY HISTORY MAIN SECTION
		get_emergency_history_tab(tabs[2], response_dict)
	#
	# Get next step
	st.markdown("---")
	session_dict = options_to_continue(session_dict)
	save_json(session_file, session_dict)



