import pandas as pd
import numpy as np
import uuid
import re
import streamlit as st
from io import BytesIO
from PIL import Image
from ..functions.color import *
import random
import string
import os


#from .file import entry_table_file
from .path import (
	get_neighbor_path,
	pages_str,
	data_str, 
	functions_str,
	load_json,
)
#from .lst import type_lst

from .query_mdm import get_seen_stages_df, get_patient_history, get_rx_df


def get_possible_diag_tab(response_dict, current_tab):
	all_diag = response_dict["high_severity_diag"]+response_dict["low_severity_diag"]+response_dict["eliminated_diag"]
	if len(all_diag) > 0:
		diag_container = current_tab.container(height=300, border=False)
		if len(response_dict["high_severity_diag"]) > 0:
			diag_container.markdown(f"#### Possible High Severity Diagnoses:")
			for i, diag in enumerate(response_dict["high_severity_diag"]):
				diag_container.markdown(f" {i+1}. {diag}")
		if len(response_dict["low_severity_diag"]) > 0:
			diag_container.markdown(f"#### Possible Low Severity Diagnoses:")
			for i, diag in enumerate(response_dict["low_severity_diag"]):
				diag_container.markdown(f" {i+1}. {diag}")
		if len(response_dict["eliminated_diag"]) > 0:
			diag_container.markdown(f"#### Deprioritized Diagnoses:")
			for i, diag in enumerate(response_dict["eliminated_diag"]):
				diag_container.markdown(f" {i+1}. {diag}")
	else:
		current_tab.markdown(f"#### No probable diagnoses yet.")

def get_rx_tab(response_dict, current_tab):
	rx_df = get_rx_df(response_dict["rx_list"])
	if len(rx_df) > 0:
		rx_columns=['Medication Name','Dose','Route','Frequency']
		col_sizes = [0.2,0.4,0.1,0.1,0.2]
		st_col_header_lst = current_tab.columns(col_sizes)
		for i, col in enumerate(['Date & Time']+rx_columns):
			st_col_header_lst[i].markdown(f"##### {col}")
		#
		rx_container = current_tab.container(height=300, border=False)
		st_col_lst = rx_container.columns(col_sizes, vertical_alignment="center")
		#
		prev_date = "None"
		for date, time, name, dose, route, freq in rx_df[['Date', 'Time']+rx_columns].values:
			if prev_date!=date:
				st_col_lst[0].markdown(get_html_text({date:gray_hex}, font_size="small"),unsafe_allow_html=True)
				for i in np.arange(len(rx_columns)):
					st_col_lst[i+1].markdown(get_html_text({" ":gray_hex}, font_size="small"),unsafe_allow_html=True)
			st_col_lst[0].markdown(get_html_text({time:gray_hex}, font_size="small"),unsafe_allow_html=True)
			prev_date = date
			#
			for i, (col, val) in enumerate(zip(rx_columns, [name, dose, route, freq])):
				st_col_lst[i+1].markdown(get_html_text({val:gray_hex}, font_size="small"),unsafe_allow_html=True)
	else:
		current_tab.markdown(f"#### No interventions yet.")

def get_start_ehr_token(session_dict):
	if session_dict["ehr_token"] == "":
		session_dict["ehr_token"] = random_token()
		st.session_state.response_dict = {}
	return session_dict

def get_mode_and_input_type(mode_selection, session_dict, canned_data):
	"""
	This functions gets the mode from side bar and updates if necessary
	"""
	if mode_selection != session_dict["mode_selection"]:
		session_dict["ehr_token"] = random_token()
		session_dict["prev_stage"] = 'Start'
	input_type = mode_selection.split()[0].lower() if mode_selection != "Canned EHRs" else canned_data
	return session_dict, input_type

def get_use_case_narrative(use_case, current_tab, prev_stage):
	left_col, right_col = current_tab.columns([0.3,0.7])
	left_col.image(f'{get_neighbor_path(__file__, functions_str, data_str)}/{use_case}/narrative_image.png', output_format="PNG")
	right_col.markdown(f"#### Situation:")
	with open(f'{get_neighbor_path(__file__, functions_str, data_str)}/{use_case}/narrative.txt', 'r') as narrative:
		lines = ' '.join([line.strip() for line in narrative.readlines()])
		right_col.markdown(f"{lines}")
	if prev_stage == 'Start':
		right_col.markdown(f"#### Current Stage:")
		right_col.markdown(f"The model is currently assessing the severity of the crew member’s symptoms. If it determines this to be an emergency, it will conduct a pain survey (see the *Emergency History* tab for results). After completing this, the model will analyze the results and determine how to proceed (see the *Next Stage* tab). ")


def get_emergency_history_tab(current_tab, response_dict):
	#current_tab.markdown("### Emergency History")
	#
	col_sizes = [0.2,0.2,0.6]
	st_col_header_lst = current_tab.columns(col_sizes)
	for i, col in enumerate(['Date & Time', 'Category', 'Actions & Observations']):
		st_col_header_lst[i].markdown(f"##### {col}")
	#
	emergency_container = current_tab.container(height=300, border=False)
	history_df = get_patient_history(response_dict)
	#
	# add history columns
	st_col_lst = emergency_container.columns(col_sizes, vertical_alignment="bottom")
	prev_date = "None"
	history_cols = ['Date', 'Time', 'Category', 'Actions & Observations', 'Flag']
	for date, time, stage, result, flag_entry in history_df[history_cols].values:
		#date_time = '%s\t%s' % (date, time) if prev_date!=date else '\t\t\t\t'+time
		#st_col_lst[0].markdown(get_html_text({date_time:gray_hex}, font_size="small"),unsafe_allow_html=True)
		if prev_date!=date:
			st_col_lst[0].markdown(get_html_text({date:gray_hex}, font_size="small"),unsafe_allow_html=True)
			st_col_lst[1].markdown(get_html_text({"______":gray_hex}, font_size="small"),unsafe_allow_html=True)
			st_col_lst[2].markdown(get_html_text({"______":gray_hex}, font_size="small"),unsafe_allow_html=True)
		st_col_lst[0].markdown(get_html_text({time:gray_hex}, font_size="small"),unsafe_allow_html=True)
		prev_date = date
		#
		#stage_dict = {'Initial Interaction':light_brown_hex, 'Pain Survey': light_orange_hex, 'Initial Assessment':light_green_hex, 'Diagnosis': light_red_hex, 'Differential Diagnosis':light_olive_hex, 'Intervention':light_blue_hex, 'Monitoring':light_purple_hex}
		st_col_lst[1].markdown(get_html_text({stage:gray_hex}, font_size="small"),unsafe_allow_html=True)
		#
		if flag_entry == True:
			st_col_lst[2].markdown(get_html_text({result:black_hex}, font_size="small", font_weight="bold"),unsafe_allow_html=True)
		else:
			st_col_lst[2].markdown(get_html_text({result:gray_hex}, font_size="small"),unsafe_allow_html=True)

def get_current_stage_tab(response_dict, current_tab):
	elapsed_time = response_dict["elapsed_time"]
	h,m = int(elapsed_time/60), elapsed_time % 60
	current_stage = response_dict["new_stage"]
	actions = response_dict["action_list"]
	# 
	stages_dict = load_json(f'{get_neighbor_path(__file__, functions_str, data_str)}/emergency_stages.json')
	#
	if len(actions) > 0:
		if type(actions) != list:
			df = pd.read_json(actions, orient='split')
			actions = list(df.name.unique())
		left_col, right_col = current_tab.columns(2)
		left_col.markdown(f"#### Stage: {current_stage}")
		left_col.markdown(f"##### Elapsed Time: h {h} m {m}")
		left_col.markdown(stages_dict[current_stage])
		right_col.markdown(f"#### ")
		right_col.markdown(f"##### Available Actions:")
		action_container = right_col.container(height=200, border=False)
		for action in actions:
			action_container.markdown(f" - {action.strip()}")
	else:
		current_tab.markdown(f"#### Stage: {current_stage}")
		current_tab.markdown(f"##### Elapsed Time: h {h} m {m}")
		current_tab.markdown(stages_dict[current_stage])
	return current_stage


def options_to_continue(session_dict):
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
	if button_cols[0].button(next_option_buttons[0], help=next_option_buttons_help[0]):
		button_pressed = next_option_buttons[0]
		session_dict["ehr_token"] = ""
		session_dict["prev_stage"] = "Start"
		session_dict["first_step"] = True
	elif button_cols[1].button(next_option_buttons[1], help=next_option_buttons_help[1]):
		button_pressed = next_option_buttons[1]
		session_dict["prev_stage"] = "Stable Health Stage"
	elif button_cols[2].button(next_option_buttons[2], help=next_option_buttons_help[2]):
		button_pressed = next_option_buttons[2]
	return session_dict

def random_token():
	length = 13
	chars = string.ascii_letters + string.digits
	random.seed = (os.urandom(1024))
	return ''.join(random.choice(chars) for i in range(length))

def get_html_text(text_color_dict, font_size="medium", font_weight="normal"):

	html_str = ""
	for text, color in text_color_dict.items():

		size = font_size
		if type(font_size) == dict:
			size = font_size[text]

		weight = font_weight
		if type(font_weight) == dict:
			weight = font_weight[text]

		html_str += f'<span style="font-family:sans-serif; font-size: {size}; font-weight: {weight}; color:{color};">{text}</span>'

	return html_str

def create_st_button(link_text, link_url, hover_color="#e78ac3", st_col=None):

	button_uuid = str(uuid.uuid4()).replace("-", "")
	button_id = re.sub("\d+", "", button_uuid)

	button_css = f"""
		<style>
			#{button_id} {{
				background-color: rgb(255, 255, 255);
				color: rgb(38, 39, 48);
				padding: 0.25em 0.38em;
				position: relative;
				text-decoration: none;
				border-radius: 4px;
				border-width: 1px;
				border-style: solid;
				border-color: rgb(230, 234, 241);
				border-image: initial;

			}}
			#{button_id}:hover {{
				border-color: {hover_color};
				color: {hover_color};
			}}
			#{button_id}:active {{
				box-shadow: none;
				background-color: {hover_color};
				color: white;
				}}
		</style> """

	html_str = f'<a href="{link_url}" target="_blank" id="{button_id}";>{link_text}</a><br></br>'

	if st_col is None:
		st.markdown(button_css + html_str, unsafe_allow_html=True)
	else:
		st_col.markdown(button_css + html_str, unsafe_allow_html=True)



