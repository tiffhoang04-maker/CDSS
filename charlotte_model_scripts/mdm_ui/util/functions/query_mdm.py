import pandas as pd
import numpy as np
import os
import requests
import re
import json

uri = "http://20.157.95.66:8080/"

#gunicorn --bind 0.0.0.0:8080 app:app --timeout 0
time_date_pattern = re.compile(r'Date: [A-Z]{1}[a-z]+ [0-9]{2} [0-9]{4} Time: [0-9]{2}:[0-9]{2}')
flag_pattern = re.compile(r'Potential Diagnoses|\(High\)|\(Low\)|Abnormal|sinus tachycardia|Confirmed diagnosis|have worsened')


def get_mdm_next_step(session_dict, input_type):
	response = requests.get('%sget_next_stage/%s/%s/%s' % (uri, input_type, session_dict["ehr_token"], session_dict["prev_stage"]))
	response_dict = response.json()
	return response_dict

def get_interactive_mdm_next_step(ehr_token, input_type, new_stage, user_inputs, next_test):
	if type(user_inputs) != dict:
		user_inputs = {"user_input": user_inputs}
	if next_test != "next":
		new_stage = '|'.join([new_stage, next_test])
	#
	data = {}
	data["input_type"] = input_type
	data["ehr_token"] = ehr_token
	data["new_stage"] = new_stage
	data["user_inputs"] = json.dumps(user_inputs)
	print(user_inputs)
	response = requests.post('%sget_next_stage_interactive/' % uri, params=data)
	response_dict = response.json()
	response_dict["prompt_dict"] = json.loads(response_dict["prompt_dict"])
	print(response_dict["prompt_dict"])
	return response_dict


def get_seen_stages_df(seen_stages):
	seen_stages_df = pd.DataFrame([split_time_date_col(stage) for stage in seen_stages], columns=['Date', 'Time', 'Stage'])
	return seen_stages_df.drop_duplicates()

def get_patient_history(response_dict):
	patient_history_df = []
	for ehr_type, ehr_values in response_dict['EHR'].items():
		for row in ehr_values.strip().split('\n'):
			if row[:4]=='Date':
				row = split_time_date_col(row)
				flag = len(flag_pattern.findall(row[-1])) >0
				patient_history_df.append(row+[ehr_type, flag])            
	patient_history_df = pd.DataFrame(patient_history_df, columns=['Date', 'Time', 'Actions & Observations', 'Category', 'Flag'])
	patient_history_df = patient_history_df[['Date', 'Time', 'Category', 'Actions & Observations', 'Flag']].sort_values(['Date', 'Time'])
	return patient_history_df

def get_rx_df(rx_list):
	columns=['Medication Name','Dose','Route','Frequency']
	rx_df = []
	for row in rx_list:
		d, t, entry = split_time_date_col(row.strip())
		rx_df.append([d,t]+entry.split('\t'))
	rx_df = pd.DataFrame(rx_df, columns=['Date', 'Time']+columns).drop_duplicates()
	return rx_df

def split_time_date_col(row):
	t, d = time_date_pattern.findall(row.strip())[0][6:].split(' Time: ')
	entry = time_date_pattern.split(row.strip())[-1].strip()
	return [t, d, entry]


